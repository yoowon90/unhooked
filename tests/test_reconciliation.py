"""Reconciliation tests — event feed drained onto ledger statuses.

plaid_client.sync_transfer_events is monkeypatched with a fake feed that
honors after_id, so cursor persistence / idempotency is tested for real.
"""
import pytest
from flask import Flask

from website import db
from website import ledger
from website import reconciliation
from website.models import User, SyncCursor
from website.reconciliation import reconcile_transfers, should_sync


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


@pytest.fixture
def user(app):
    u = User(email='t@example.com', first_name='Boo', password='x', zipcode='10001')
    db.session.add(u)
    db.session.commit()
    return u


def _pending_txn(user, amount_cents, transfer_id):
    txn = ledger.transfer_to_savings(user.id, amount_cents)
    txn.provider_transfer_id = transfer_id
    db.session.commit()
    return txn


def _feed(monkeypatch, events):
    """Install a fake event feed that honors after_id like the real API."""
    def fake_sync(after_id=0, count=25):
        return [e for e in events if e['event_id'] > after_id][:count]
    monkeypatch.setattr(reconciliation.plaid_client, 'sync_transfer_events', fake_sync)
    monkeypatch.setattr(reconciliation.plaid_client, 'is_configured', lambda: True)


def test_settled_event_settles_txn_and_advances_cursor(user, monkeypatch):
    txn = _pending_txn(user, 4250, 'tr-1')
    _feed(monkeypatch, [
        {'event_id': 1, 'transfer_id': 'tr-1', 'event_type': 'pending'},
        {'event_id': 2, 'transfer_id': 'tr-1', 'event_type': 'posted'},
        {'event_id': 3, 'transfer_id': 'tr-1', 'event_type': 'settled'},
    ])
    summary = reconcile_transfers()

    assert txn.status == 'settled' and txn.settled_at is not None
    assert summary['settled'] == 1 and summary['events'] == 3
    assert summary['cursor'] == 3
    assert SyncCursor.query.filter_by(name='plaid_transfer_events').first().last_event_id == 3


def test_rerun_is_idempotent(user, monkeypatch):
    txn = _pending_txn(user, 1000, 'tr-1')
    _feed(monkeypatch, [{'event_id': 1, 'transfer_id': 'tr-1', 'event_type': 'settled'}])
    reconcile_transfers()
    summary2 = reconcile_transfers()  # cursor is past event 1 -> feed is empty
    assert summary2['events'] == 0
    assert txn.status == 'settled'


def test_failed_event_fails_txn_with_reason_in_memo(user, monkeypatch):
    txn = _pending_txn(user, 1000, 'tr-2')
    _feed(monkeypatch, [{
        'event_id': 5, 'transfer_id': 'tr-2', 'event_type': 'failed',
        'failure_reason': {'ach_return_code': 'R01', 'description': 'Insufficient funds'},
    }])
    summary = reconcile_transfers()

    assert txn.status == 'failed'
    assert 'Insufficient funds' in txn.memo
    assert summary['failed'] == 1


def test_return_after_settlement_reverses_and_restores_balance(user, monkeypatch):
    """The classic recon edge: ACH return arrives AFTER we already settled."""
    txn = _pending_txn(user, 5000, 'tr-3')
    accounts = ledger.get_or_create_accounts(user.id)

    _feed(monkeypatch, [{'event_id': 1, 'transfer_id': 'tr-3', 'event_type': 'settled'}])
    reconcile_transfers()
    assert txn.status == 'settled'
    assert ledger.account_balance_cents(accounts['savings'].id) == 5000

    _feed(monkeypatch, [
        {'event_id': 1, 'transfer_id': 'tr-3', 'event_type': 'settled'},
        {'event_id': 2, 'transfer_id': 'tr-3', 'event_type': 'returned',
         'failure_reason': {'ach_return_code': 'R10'}},
    ])
    summary = reconcile_transfers()  # cursor at 1, so only the return applies

    assert summary['returned'] == 1
    assert txn.status == 'returned'
    # reversal posted, balances back to zero, history intact (2 txns + reversal)
    assert ledger.account_balance_cents(accounts['savings'].id) == 0
    assert ledger.account_balance_cents(accounts['checking'].id) == 0


def test_return_while_still_pending_just_fails(user, monkeypatch):
    txn = _pending_txn(user, 1000, 'tr-4')
    _feed(monkeypatch, [{'event_id': 1, 'transfer_id': 'tr-4', 'event_type': 'returned'}])
    summary = reconcile_transfers()
    assert txn.status == 'failed' and summary['failed'] == 1


def test_unmatched_transfer_is_flagged_not_swallowed(user, monkeypatch):
    _feed(monkeypatch, [{'event_id': 1, 'transfer_id': 'tr-ghost', 'event_type': 'settled'}])
    summary = reconcile_transfers()
    assert summary['unmatched'] == ['tr-ghost']
    assert summary['settled'] == 0


def test_unknown_event_types_ignored_but_cursor_advances(user, monkeypatch):
    _pending_txn(user, 1000, 'tr-5')
    _feed(monkeypatch, [{'event_id': 9, 'transfer_id': 'tr-5', 'event_type': 'sweep.settled'}])
    summary = reconcile_transfers()
    assert summary['cursor'] == 9  # never re-fetch what we've seen


def test_pagination_drains_multiple_pages(user, monkeypatch):
    txns = [_pending_txn(user, 100 + i, f'tr-p{i}') for i in range(3)]
    events = [{'event_id': i + 1, 'transfer_id': f'tr-p{i}', 'event_type': 'settled'}
              for i in range(3)]

    def tiny_pages(after_id=0, count=25):
        remaining = [e for e in events if e['event_id'] > after_id]
        return remaining[:1]  # force one event per page
    monkeypatch.setattr(reconciliation.plaid_client, 'sync_transfer_events', tiny_pages)

    summary = reconcile_transfers()
    assert summary['settled'] == 3
    assert all(t.status == 'settled' for t in txns)


def test_should_sync_guard(user, monkeypatch):
    monkeypatch.setattr(reconciliation.plaid_client, 'is_configured', lambda: True)
    assert should_sync() is False          # nothing in flight
    txn = ledger.transfer_to_savings(user.id, 1000)
    assert should_sync() is False          # pending but never originated
    txn.provider_transfer_id = 'tr-x'
    db.session.commit()
    assert should_sync() is True           # originated + pending
    ledger.settle_transaction(txn)
    assert should_sync() is False          # terminal
