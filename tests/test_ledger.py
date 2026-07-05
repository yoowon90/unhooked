"""Ledger core tests — run with:  python -m pytest tests/ -v

Uses an in-memory SQLite database (never touches instance/database_dev.db).
These tests prove the two properties that make this a ledger rather than a
balance column: every posting balances to zero, and balances are derived.
"""
import pytest
from flask import Flask

from website import db
from website.models import User, LedgerAccount, LedgerEntry, LedgerTransaction
from website import ledger
from website.ledger import LedgerError


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'  # in-memory
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


@pytest.fixture
def user(app):
    u = User(email='test@example.com', first_name='Test', password='x', zipcode='10001')
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def other_user(app):
    u = User(email='other@example.com', first_name='Other', password='x', zipcode='10001')
    db.session.add(u)
    db.session.commit()
    return u


# ── dollars_to_cents ──────────────────────────────────────────────────────────

def test_dollars_to_cents_handles_float_artifacts():
    assert ledger.dollars_to_cents(79.99) == 7999
    assert ledger.dollars_to_cents(110.10) == 11010
    assert ledger.dollars_to_cents('19.99') == 1999
    assert ledger.dollars_to_cents(0.1) == 10
    assert ledger.dollars_to_cents(100) == 10000
    # HALF_UP at the sub-cent boundary
    assert ledger.dollars_to_cents('1.005') == 101


def test_dollars_to_cents_rejects_garbage():
    with pytest.raises(LedgerError):
        ledger.dollars_to_cents('not money')
    with pytest.raises(LedgerError):
        ledger.dollars_to_cents(None)


def test_format_cents():
    assert ledger.format_cents(123456) == '$1,234.56'
    assert ledger.format_cents(-500) == '-$5.00'
    assert ledger.format_cents(0) == '$0.00'


# ── accounts ──────────────────────────────────────────────────────────────────

def test_get_or_create_accounts_is_idempotent(user):
    first = ledger.get_or_create_accounts(user.id)
    second = ledger.get_or_create_accounts(user.id)
    assert set(first) == {'checking', 'savings'}
    assert first['checking'].id == second['checking'].id
    assert LedgerAccount.query.filter_by(user_id=user.id).count() == 2


def test_account_has_no_stored_balance_column(user):
    """Balance must be derived — a mutable balance column is the classic
    lost-update bug this design exists to avoid."""
    account = ledger.get_or_create_accounts(user.id)['savings']
    assert not hasattr(account, 'balance')
    assert not hasattr(account, 'balance_cents')


# ── post_transaction: the invariant ───────────────────────────────────────────

def test_balanced_transfer_posts_and_balances_derive(user):
    accounts = ledger.get_or_create_accounts(user.id)
    txn = ledger.post_transaction(
        user.id,
        entries=[(accounts['checking'].id, -8000), (accounts['savings'].id, 8000)],
        memo='Savings match for WishItem #45',
    )
    assert txn.status == 'pending'
    assert txn.amount_cents == 8000
    assert sum(e.amount_cents for e in txn.entries) == 0
    assert ledger.account_balance_cents(accounts['checking'].id) == -8000
    assert ledger.account_balance_cents(accounts['savings'].id) == 8000


def test_balance_is_sum_over_all_transactions(user):
    accounts = ledger.get_or_create_accounts(user.id)
    for amount in (1000, 2500, 425):
        ledger.transfer_to_savings(user.id, amount)
    assert ledger.account_balance_cents(accounts['savings'].id) == 3925
    assert ledger.account_balance_cents(accounts['checking'].id) == -3925


def test_unbalanced_entries_rejected_and_nothing_persists(user):
    accounts = ledger.get_or_create_accounts(user.id)
    with pytest.raises(LedgerError, match='sum to zero'):
        ledger.post_transaction(
            user.id,
            entries=[(accounts['checking'].id, -8000), (accounts['savings'].id, 7999)],
        )
    assert LedgerTransaction.query.count() == 0
    assert LedgerEntry.query.count() == 0


def test_single_entry_rejected(user):
    accounts = ledger.get_or_create_accounts(user.id)
    with pytest.raises(LedgerError, match='at least 2'):
        ledger.post_transaction(user.id, entries=[(accounts['savings'].id, 100)])


def test_zero_and_non_integer_amounts_rejected(user):
    accounts = ledger.get_or_create_accounts(user.id)
    a, b = accounts['checking'].id, accounts['savings'].id
    with pytest.raises(LedgerError, match='non-zero'):
        ledger.post_transaction(user.id, entries=[(a, 0), (b, 0)])
    with pytest.raises(LedgerError, match='integer cents'):
        ledger.post_transaction(user.id, entries=[(a, -80.0), (b, 80.0)])
    with pytest.raises(LedgerError, match='integer cents'):
        ledger.post_transaction(user.id, entries=[(a, True), (b, -1)])


def test_cannot_post_to_another_users_account(user, other_user):
    theirs = ledger.get_or_create_accounts(other_user.id)
    with pytest.raises(LedgerError, match='do not belong'):
        ledger.post_transaction(
            user.id,
            entries=[(theirs['checking'].id, -100), (theirs['savings'].id, 100)],
        )
    assert LedgerTransaction.query.count() == 0


def test_unknown_account_rejected(user):
    accounts = ledger.get_or_create_accounts(user.id)
    with pytest.raises(LedgerError, match='Unknown ledger account'):
        ledger.post_transaction(
            user.id,
            entries=[(accounts['checking'].id, -100), (99999, 100)],
        )


# ── transfer_to_savings ───────────────────────────────────────────────────────

def test_transfer_to_savings_convenience(user):
    txn = ledger.transfer_to_savings(user.id, 7999, wishitem_id=None, memo='Savings match')
    assert txn.status == 'pending'
    assert txn.amount_cents == 7999
    legs = sorted(e.amount_cents for e in txn.entries)
    assert legs == [-7999, 7999]


def test_transfer_to_savings_rejects_non_positive(user):
    with pytest.raises(LedgerError, match='positive'):
        ledger.transfer_to_savings(user.id, 0)
    with pytest.raises(LedgerError, match='positive'):
        ledger.transfer_to_savings(user.id, -500)


# ── lifecycle ─────────────────────────────────────────────────────────────────

def test_settle_and_fail_lifecycle(user):
    txn = ledger.transfer_to_savings(user.id, 1000)
    ledger.settle_transaction(txn)
    assert txn.status == 'settled'
    assert txn.settled_at is not None
    with pytest.raises(LedgerError, match='Only pending'):
        ledger.settle_transaction(txn)  # settled -> settled is not a move

    txn2 = ledger.transfer_to_savings(user.id, 1000)
    ledger.fail_transaction(txn2)
    assert txn2.status == 'failed'
    with pytest.raises(LedgerError, match='Only pending'):
        ledger.fail_transaction(txn2)


def test_reversal_restores_balance_without_deleting_history(user):
    accounts = ledger.get_or_create_accounts(user.id)
    txn = ledger.transfer_to_savings(user.id, 5000)
    reversal = ledger.reverse_transaction(txn)

    # net zero again…
    assert ledger.account_balance_cents(accounts['savings'].id) == 0
    assert ledger.account_balance_cents(accounts['checking'].id) == 0
    # …but BOTH transactions remain: history is append-only.
    assert LedgerTransaction.query.count() == 2
    assert LedgerEntry.query.count() == 4
    assert f'Reversal of txn #{txn.id}' == reversal.memo
