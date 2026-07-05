"""Shared purchase-flow tests (mark_purchased + record_savings_decision)."""
import datetime

import pytest
from flask import Flask

from website import db
from website import ledger
from website.ledger import LedgerError
from website.models import User, WishItem, LedgerTransaction
from website.purchases import mark_purchased, needs_savings_prompt, record_savings_decision


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
def item(user):
    i = WishItem(
        user_id=user.id,
        name='Wool Coat',
        brand='Acme',
        category='Outerwear',
        price=79.99,
        link='https://example.com/coat',
        date=datetime.datetime.now() - datetime.timedelta(days=12),
    )
    db.session.add(i)
    db.session.commit()
    return i


def test_mark_purchased_stamps_everything(user, item):
    mark_purchased(item, user)
    assert item.purchased is True
    assert item.unhooked is False
    assert item.purchase_date is not None
    assert item.wish_period is not None
    assert 11 <= item.wish_period.days <= 12
    assert user.last_purchase_date == item.purchase_date


def test_needs_savings_prompt_lifecycle(user, item):
    assert needs_savings_prompt(item) is False  # not purchased yet
    mark_purchased(item, user)
    assert needs_savings_prompt(item) is True   # purchased, undecided
    record_savings_decision(item, user, 'declined')
    assert needs_savings_prompt(item) is False  # decided


def test_decision_moved_posts_pending_ledger_txn(user, item):
    mark_purchased(item, user)
    record_savings_decision(item, user, 'moved', amount_cents=6500)

    assert item.savings_decision == 'moved'
    assert item.savings_txn_id is not None
    txn = item.savings_txn
    assert txn.status == 'pending'
    assert txn.amount_cents == 6500  # the edited amount, not the item price
    assert txn.wishitem_id == item.id
    accounts = ledger.get_or_create_accounts(user.id)
    assert ledger.account_balance_cents(accounts['savings'].id) == 6500


def test_decision_declined_posts_nothing(user, item):
    mark_purchased(item, user)
    record_savings_decision(item, user, 'declined')
    assert item.savings_decision == 'declined'
    assert item.savings_txn_id is None
    assert LedgerTransaction.query.count() == 0


def test_decision_is_recorded_once(user, item):
    mark_purchased(item, user)
    record_savings_decision(item, user, 'moved', amount_cents=1000)
    with pytest.raises(LedgerError, match='already recorded'):
        record_savings_decision(item, user, 'moved', amount_cents=1000)
    # No double-post:
    assert LedgerTransaction.query.count() == 1


def test_decision_requires_purchased_item(user, item):
    with pytest.raises(LedgerError, match='purchased items'):
        record_savings_decision(item, user, 'declined')


def test_moved_requires_positive_amount(user, item):
    mark_purchased(item, user)
    with pytest.raises(LedgerError):
        record_savings_decision(item, user, 'moved', amount_cents=0)
    with pytest.raises(LedgerError):
        record_savings_decision(item, user, 'moved', amount_cents=None)
    assert item.savings_decision is None  # nothing recorded on failure


def test_invalid_decision_rejected(user, item):
    mark_purchased(item, user)
    with pytest.raises(LedgerError, match='decision must be'):
        record_savings_decision(item, user, 'maybe')
