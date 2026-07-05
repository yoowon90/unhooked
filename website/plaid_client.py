"""Thin client for the Plaid REST API (sandbox).

Deliberately raw HTTP (requests) rather than the plaid-python SDK so the
actual API shapes stay visible — the point of this integration is learning
what a banking-partner API looks like on the wire. Every Plaid call is a
POST with client_id/secret in the JSON body.

Env keys (.env): PLAID_CLIENT_ID, PLAID_SANDBOX_SECRET (or PLAID_SECRET),
PLAID_ENV (defaults to 'sandbox' — this app should stay in sandbox; real
fund movement is a compliance project, not a code one).
"""
import os
import uuid

import requests

PLAID_HOSTS = {
    'sandbox': 'https://sandbox.plaid.com',
    'production': 'https://production.plaid.com',
}


class PlaidError(RuntimeError):
    """Raised on any non-2xx Plaid response. Carries the parsed error body."""

    def __init__(self, endpoint, body):
        self.endpoint = endpoint
        self.error_type = body.get('error_type')
        self.error_code = body.get('error_code')
        self.message = body.get('error_message') or str(body)
        super().__init__(f'{endpoint}: [{self.error_code}] {self.message}')


def _base_url():
    env = os.getenv('PLAID_ENV', 'sandbox')
    return PLAID_HOSTS.get(env, PLAID_HOSTS['sandbox'])


def _credentials():
    client_id = os.getenv('PLAID_CLIENT_ID')
    secret = os.getenv('PLAID_SANDBOX_SECRET') or os.getenv('PLAID_SECRET')
    if not client_id or not secret:
        raise PlaidError('credentials', {
            'error_code': 'MISSING_KEYS',
            'error_message': 'PLAID_CLIENT_ID and PLAID_SANDBOX_SECRET must be set in .env',
        })
    return client_id, secret


def is_configured():
    return bool(os.getenv('PLAID_CLIENT_ID')
                and (os.getenv('PLAID_SANDBOX_SECRET') or os.getenv('PLAID_SECRET')))


def _post(endpoint, payload):
    client_id, secret = _credentials()
    body = {'client_id': client_id, 'secret': secret, **payload}
    resp = requests.post(f'{_base_url()}{endpoint}', json=body, timeout=30)
    data = resp.json()
    if resp.status_code != 200:
        raise PlaidError(endpoint, data)
    return data


# ── Link + item lifecycle ─────────────────────────────────────────────────────

def create_link_token(user_id):
    """Start the Link flow. The returned link_token initializes Plaid Link
    in the browser; it expires in ~4 hours."""
    data = _post('/link/token/create', {
        'user': {'client_user_id': str(user_id)},
        'client_name': 'Unhooked',
        'products': ['auth'],  # auth = account/routing verification, required for transfers
        'country_codes': ['US'],
        'language': 'en',
        'account_filters': {
            'depository': {'account_subtypes': ['checking', 'savings']},
        },
    })
    return data['link_token']


def exchange_public_token(public_token):
    """Link's onSuccess public_token -> permanent access_token + item_id."""
    data = _post('/item/public_token/exchange', {'public_token': public_token})
    return {'access_token': data['access_token'], 'item_id': data['item_id']}


def get_accounts(access_token):
    """List the accounts on the linked item (id, name, type, subtype, mask)."""
    data = _post('/accounts/get', {'access_token': access_token})
    return data['accounts']


def get_institution_name(access_token):
    """Best-effort display name of the linked bank; None on any failure."""
    try:
        item = _post('/item/get', {'access_token': access_token})['item']
        inst_id = item.get('institution_id')
        if not inst_id:
            return None
        inst = _post('/institutions/get_by_id', {
            'institution_id': inst_id, 'country_codes': ['US'],
        })
        return inst['institution']['name']
    except PlaidError:
        return None


def remove_item(access_token):
    """Revoke the access token at Plaid (called on disconnect)."""
    _post('/item/remove', {'access_token': access_token})


# ── Transfer (ACH rail) ───────────────────────────────────────────────────────

def create_transfer_authorization(access_token, account_id, amount_dollars_str,
                                  legal_name, idempotency_key=None):
    """Step 1 of a transfer: Plaid runs risk/balance checks and returns an
    authorization with decision 'approved' or 'declined'. `type: debit` pulls
    money FROM the user's account (the 'collect' leg of an ACH flow).
    The idempotency_key makes retries safe — same key, same authorization,
    no double-pull."""
    data = _post('/transfer/authorization/create', {
        'access_token': access_token,
        'account_id': account_id,
        'type': 'debit',
        'network': 'ach',
        'amount': amount_dollars_str,   # Plaid wants a decimal STRING, e.g. "65.00"
        'ach_class': 'ppd',             # SEC code: Prearranged Payment (consumer-authorized)
        'user': {'legal_name': legal_name},
        'idempotency_key': idempotency_key or str(uuid.uuid4()),
    })
    return data['authorization']


def create_transfer(access_token, account_id, authorization_id, description='Savings'):
    """Step 2: originate the transfer under an approved authorization.
    description is what shows on the bank statement (max 15 chars)."""
    data = _post('/transfer/create', {
        'access_token': access_token,
        'account_id': account_id,
        'authorization_id': authorization_id,
        'description': description[:15],
    })
    return data['transfer']


def get_transfer(transfer_id):
    """Current status of one transfer (pending/posted/settled/failed/returned)."""
    data = _post('/transfer/get', {'transfer_id': transfer_id})
    return data['transfer']


def sync_transfer_events(after_id=0, count=25):
    """Cursor over transfer status-change events — the reconciliation feed
    (step 5). after_id is the last event_id already processed."""
    data = _post('/transfer/event/sync', {'after_id': after_id, 'count': count})
    return data['transfer_events']


# ── Sandbox-only helpers ──────────────────────────────────────────────────────

def sandbox_create_public_token(institution_id='ins_109508'):
    """Create a Link public_token without the browser UI — sandbox's headless
    test path (ins_109508 = 'First Platypus Bank'). Used by tests/smoke."""
    data = _post('/sandbox/public_token/create', {
        'institution_id': institution_id,
        'initial_products': ['auth'],
    })
    return data['public_token']


def sandbox_simulate_transfer_event(transfer_id, event_type):
    """Force a sandbox transfer through its lifecycle ('posted', 'settled',
    'failed', 'returned' — bare names, not 'transfer.'-prefixed) so
    reconciliation can be exercised without waiting for simulated ACH
    timing."""
    _post('/sandbox/transfer/simulate', {
        'transfer_id': transfer_id,
        'event_type': event_type,
    })
