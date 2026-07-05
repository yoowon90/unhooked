"""Ledger core — double-entry posting logic.

The ledger is the app's internal source of truth for money movement; the real
bank (Plaid Transfer, steps 4-5) is the outside world that we reconcile
against. Rules enforced here:

1. Every transaction is >= 2 entries that SUM TO ZERO (money moves, it is
   never created or destroyed). Enforced in Python, not as a DB constraint —
   SQLite (dev) enforces constraints more laxly than Postgres (prod), so a
   DB-only guard could pass silently on dev and only blow up in prod.
2. All amounts are INTEGER CENTS. Convert at the boundary with
   dollars_to_cents(); never do float math on money.
3. Entries are immutable. Fix mistakes with reverse_transaction(), never by
   editing rows.
4. Balances are DERIVED (SUM over entries), never stored on the account.
   Posting locks the account rows (SELECT ... FOR UPDATE) so concurrent
   postings serialize on Postgres; SQLAlchemy's SQLite dialect ignores
   FOR UPDATE, which is fine because SQLite serializes writers anyway.
"""
import datetime
from decimal import Decimal, ROUND_HALF_UP

from . import db
from .models import (
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    LEDGER_ACCOUNT_KINDS,
)


class LedgerError(ValueError):
    """Raised when a posting would violate a ledger invariant."""


# ── Money conversion (boundary only) ──────────────────────────────────────────

def dollars_to_cents(amount):
    """Convert a dollar amount (float, str, int, or Decimal) to integer cents.

    Goes through Decimal(str(...)) so float artifacts like 79.99 -> 7998.99...
    round correctly instead of truncating a cent.
    """
    if amount is None:
        raise LedgerError('Amount is required')
    try:
        cents = (Decimal(str(amount)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    except Exception:
        raise LedgerError(f'Not a valid money amount: {amount!r}')
    return int(cents)


def format_cents(cents):
    """Integer cents -> display string, e.g. 123456 -> '$1,234.56'."""
    sign = '-' if cents < 0 else ''
    return f'{sign}${abs(cents) / 100:,.2f}'


# ── Accounts ──────────────────────────────────────────────────────────────────

def get_or_create_accounts(user_id):
    """Return {'checking': LedgerAccount, 'savings': LedgerAccount} for the
    user, creating the buckets on first touch."""
    accounts = {a.kind: a for a in LedgerAccount.query.filter_by(user_id=user_id).all()}
    created = False
    for kind in LEDGER_ACCOUNT_KINDS:
        if kind not in accounts:
            account = LedgerAccount(
                user_id=user_id,
                kind=kind,
                display_name=kind.capitalize(),
            )
            db.session.add(account)
            accounts[kind] = account
            created = True
    if created:
        db.session.commit()
    return accounts


def account_balance_cents(account_id):
    """Derived balance: SUM of the account's entries. Never stored."""
    total = (
        db.session.query(db.func.coalesce(db.func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.account_id == account_id)
        .scalar()
    )
    return int(total)


# ── Posting ───────────────────────────────────────────────────────────────────

def post_transaction(user_id, entries, memo='', wishitem_id=None,
                     status='pending', provider_transfer_id=None):
    """Atomically post one transaction.

    `entries` is an iterable of (account_id, amount_cents) legs. Validates the
    double-entry invariants, locks the accounts, and commits. Returns the
    LedgerTransaction. Raises LedgerError (and leaves the session clean) on
    any violation.
    """
    entries = list(entries)
    if len(entries) < 2:
        raise LedgerError('A transaction needs at least 2 entries (double-entry)')

    for account_id, amount_cents in entries:
        # bool is an int subclass — reject it explicitly along with floats.
        if isinstance(amount_cents, bool) or not isinstance(amount_cents, int):
            raise LedgerError(f'Entry amounts must be integer cents, got {amount_cents!r}')
        if amount_cents == 0:
            raise LedgerError('Entry amounts must be non-zero')

    balance = sum(amount for _, amount in entries)
    if balance != 0:
        raise LedgerError(f'Entries must sum to zero, got {balance}')

    # Lock the accounts in deterministic (id) order so two concurrent postings
    # can't deadlock. FOR UPDATE is real on Postgres, ignored on SQLite.
    account_ids = sorted({account_id for account_id, _ in entries})
    accounts = (
        LedgerAccount.query
        .filter(LedgerAccount.id.in_(account_ids))
        .order_by(LedgerAccount.id)
        .with_for_update()
        .all()
    )
    found = {a.id for a in accounts}
    missing = [i for i in account_ids if i not in found]
    if missing:
        db.session.rollback()
        raise LedgerError(f'Unknown ledger account(s): {missing}')
    not_owned = [a.id for a in accounts if a.user_id != user_id]
    if not_owned:
        db.session.rollback()
        raise LedgerError(f'Account(s) {not_owned} do not belong to user {user_id}')
    if len({a.currency for a in accounts}) > 1:
        db.session.rollback()
        raise LedgerError('All entries in a transaction must share one currency')

    txn = LedgerTransaction(
        user_id=user_id,
        wishitem_id=wishitem_id,
        amount_cents=sum(amount for _, amount in entries if amount > 0),
        status=status,
        memo=memo or '',
        provider_transfer_id=provider_transfer_id,
    )
    db.session.add(txn)
    db.session.flush()  # assign txn.id for the entry FKs
    for account_id, amount_cents in entries:
        db.session.add(LedgerEntry(
            transaction_id=txn.id,
            account_id=account_id,
            amount_cents=amount_cents,
        ))
    db.session.commit()
    return txn


def transfer_to_savings(user_id, amount_cents, wishitem_id=None, memo=''):
    """Convenience: post a pending checking -> savings transfer."""
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents <= 0:
        raise LedgerError('Transfer amount must be a positive integer number of cents')
    accounts = get_or_create_accounts(user_id)
    return post_transaction(
        user_id,
        entries=[
            (accounts['checking'].id, -amount_cents),
            (accounts['savings'].id, amount_cents),
        ],
        memo=memo or 'Savings match',
        wishitem_id=wishitem_id,
        status='pending',
    )


# ── Lifecycle (used by step 5 reconciliation) ─────────────────────────────────

def settle_transaction(txn):
    """pending -> settled, stamping settled_at."""
    if txn.status != 'pending':
        raise LedgerError(f'Only pending transactions can settle (txn {txn.id} is {txn.status})')
    txn.status = 'settled'
    txn.settled_at = datetime.datetime.now()
    db.session.commit()
    return txn


def fail_transaction(txn):
    """pending -> failed. The intent is void; reconciliation may also post a
    reversal if the failed transfer had already been counted anywhere."""
    if txn.status != 'pending':
        raise LedgerError(f'Only pending transactions can fail (txn {txn.id} is {txn.status})')
    txn.status = 'failed'
    db.session.commit()
    return txn


def reverse_transaction(txn, memo=None):
    """Post a NEW transaction with negated entries. This is how mistakes are
    corrected — entries are never edited or deleted, so history stays intact."""
    return post_transaction(
        txn.user_id,
        entries=[(e.account_id, -e.amount_cents) for e in txn.entries],
        memo=memo or f'Reversal of txn #{txn.id}',
        wishitem_id=txn.wishitem_id,
        status='settled',  # a reversal is an internal correction; nothing external to await
    )
