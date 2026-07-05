"""Bridge between the internal ledger and the external ACH rail (Plaid).

Separation of concerns, and the core fintech mental model:
  - website/ledger.py is the SOURCE OF TRUTH for intent (what should move).
  - Plaid Transfer is the OUTSIDE WORLD (what actually moves).
  - This module connects the two: it originates a real (sandbox) ACH debit
    for an already-posted ledger transaction and stamps provider_transfer_id.
  - Reconciliation (step 5) closes the loop by syncing Plaid's event feed
    back onto ledger transaction statuses.

Origination failure NEVER un-posts the ledger transaction — the intent
stands, provider_transfer_id stays NULL, and the transfer can be retried.
"""
from . import db
from . import plaid_client
from .crypto import decrypt_token
from .models import LedgerAccount
from .plaid_client import PlaidError


def bank_connected(user):
    return bool(user.plaid_access_token_enc)


def connect_bank(user, public_token):
    """Finish the Link flow: exchange the public_token, store the encrypted
    access token, and map the linked bank accounts onto the user's ledger
    buckets (LedgerAccount.provider_account_id)."""
    from .crypto import encrypt_token
    from .ledger import get_or_create_accounts

    exchanged = plaid_client.exchange_public_token(public_token)
    access_token = exchanged['access_token']

    user.plaid_access_token_enc = encrypt_token(access_token)
    user.plaid_item_id = exchanged['item_id']
    user.plaid_institution_name = plaid_client.get_institution_name(access_token)

    # Map Plaid accounts -> ledger buckets by depository subtype. First match
    # wins; sandbox institutions expose one checking and one savings account.
    accounts = get_or_create_accounts(user.id)
    for plaid_account in plaid_client.get_accounts(access_token):
        subtype = plaid_account.get('subtype')
        if subtype in ('checking', 'savings') and not accounts[subtype].provider_account_id:
            accounts[subtype].provider_account_id = plaid_account['account_id']
            accounts[subtype].display_name = (
                f"{plaid_account.get('name', subtype.capitalize())} ••{plaid_account.get('mask', '')}"
            )
    db.session.commit()

    # Any savings decision made before the bank existed is a standing
    # instruction — fulfill it now that we can.
    originate_pending_transfers(user)
    return user


def disconnect_bank(user):
    """Revoke the token at Plaid (best-effort) and clear the local link.
    Ledger history is untouched — it's ours, not Plaid's."""
    try:
        access_token = decrypt_token(user.plaid_access_token_enc)
        if access_token:
            plaid_client.remove_item(access_token)
    except (PlaidError, Exception):
        pass  # revocation is best-effort; local disconnect always proceeds
    user.plaid_access_token_enc = None
    user.plaid_item_id = None
    user.plaid_institution_name = None
    for account in LedgerAccount.query.filter_by(user_id=user.id).all():
        account.provider_account_id = None
    db.session.commit()
    return user


def originate_pending_transfers(user):
    """Originate every ledger transaction still awaiting a rail transfer
    (pending, no provider id). The user's 'Yes' at the interstitial IS the
    instruction to move money — if origination couldn't happen then (no bank
    linked, transient decline), the system retries here rather than asking
    the user again. Called when a bank is connected and on every
    reconciliation run ('push' before the event-feed 'pull').

    Returns {'originated': n, 'skipped': n, 'failures': [detail, ...]}.
    """
    from .models import LedgerTransaction

    summary = {'originated': 0, 'skipped': 0, 'failures': []}
    if not bank_connected(user):
        return summary
    stuck = (LedgerTransaction.query
             .filter_by(user_id=user.id, status='pending', provider_transfer_id=None)
             .all())
    for txn in stuck:
        result = originate_savings_transfer(user, txn)
        if result['originated']:
            summary['originated'] += 1
        elif result['reason'] == 'not_connected':
            summary['skipped'] += 1
        else:
            summary['failures'].append(result['detail'])
    return summary


def originate_savings_transfer(user, txn):
    """Originate the ACH debit leg for a posted ledger transaction.

    Returns a result dict (never raises on rail errors):
      {'originated': True,  'transfer_id': ...}                    on success
      {'originated': False, 'reason': 'not_connected'|'declined'|'error',
       'detail': ...}                                              otherwise

    Two-leg note: a checking -> savings self-transfer is really an ACH debit
    from checking (collect) followed by a credit to savings (disburse) once
    the debit settles — that ordering is how real platforms avoid fronting
    money that may fail to arrive. We originate the debit leg here; the
    credit leg belongs to step-5 reconciliation ("on settle").
    """
    if not bank_connected(user):
        return {'originated': False, 'reason': 'not_connected',
                'detail': 'No bank linked — transfer recorded in ledger only.'}

    checking = LedgerAccount.query.filter_by(user_id=user.id, kind='checking').first()
    if not checking or not checking.provider_account_id:
        return {'originated': False, 'reason': 'not_connected',
                'detail': 'No checking account mapped — relink your bank.'}

    access_token = decrypt_token(user.plaid_access_token_enc)
    amount_str = '%.2f' % (txn.amount_cents / 100)
    # Deterministic idempotency key: retrying origination for the same ledger
    # txn can never double-pull money. Derived from id + created_at (not id
    # alone!) — row ids can be reused after deletes, and Plaid remembers keys
    # for 48h; a reused id with different params raises
    # TRANSFER_IDEM_KEY_PARAMS_MISMATCH (found the hard way in sandbox).
    idempotency_key = f'unhooked-txn-{txn.id}-{int(txn.created_at.timestamp())}'

    try:
        authorization = plaid_client.create_transfer_authorization(
            access_token, checking.provider_account_id, amount_str,
            legal_name=user.first_name or 'Unhooked User',
            idempotency_key=idempotency_key,
        )
        if authorization['decision'] != 'approved':
            detail = (authorization.get('decision_rationale') or {}).get('description') \
                     or authorization['decision']
            return {'originated': False, 'reason': 'declined', 'detail': detail}

        transfer = plaid_client.create_transfer(
            access_token, checking.provider_account_id, authorization['id'],
            description='Savings',
        )
    except PlaidError as e:
        return {'originated': False, 'reason': 'error', 'detail': str(e)}

    txn.provider_transfer_id = transfer['id']
    db.session.commit()
    return {'originated': True, 'transfer_id': transfer['id']}
