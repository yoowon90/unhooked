"""Shopping Habits Score v3 — savings follow-through signal."""
import datetime

import pytest
from flask import Flask

from website import db
from website.models import User, WishItem
from website.reports import compute_shopping_habits_score, SCORE_WEIGHTS


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'  # in-memory
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def _make_user(email):
    u = User(email=email, first_name='Test', password='x', zipcode='10001')
    db.session.add(u)
    db.session.commit()
    return u


def _add_purchase(user, savings_decision=None, wait_days=10):
    """Purchase decided yesterday after a 7-29 day wait (0 waiting-time points),
    so the only variable across tests is the savings decision."""
    now = datetime.datetime.now()
    item = WishItem(
        user_id=user.id,
        name='Item', brand='Acme', category='Tops', price=50.0,
        link='https://example.com/x',
        purchased=True,
        purchase_date=now - datetime.timedelta(days=1),
        date=now - datetime.timedelta(days=1 + wait_days),
        wish_period=datetime.timedelta(days=wait_days),
        savings_decision=savings_decision,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _score(user):
    return compute_shopping_habits_score(user)['score']


def test_moved_and_declined_shift_score_by_savings_bucket(app):
    u_none = _make_user('a@example.com')
    _add_purchase(u_none, savings_decision=None)
    u_moved = _make_user('b@example.com')
    _add_purchase(u_moved, savings_decision='moved')
    u_declined = _make_user('c@example.com')
    _add_purchase(u_declined, savings_decision='declined')

    s_none, s_moved, s_declined = _score(u_none), _score(u_moved), _score(u_declined)
    assert s_moved - s_none == SCORE_WEIGHTS['savings_bucket']['moved']
    assert s_declined - s_none == SCORE_WEIGHTS['savings_bucket']['declined']


def test_none_decision_is_neutral_for_old_purchases(app):
    """Purchases predating the feature (savings_decision NULL) must score
    identically to how they scored in v2."""
    user = _make_user('old@example.com')
    _add_purchase(user, savings_decision=None)
    # v2 expectation: base 50 + wait bucket 0 + ratio bonus -5 (0 unhooks) = 45
    assert _score(user) == 45


def test_savings_points_apply_per_purchase(app):
    u1 = _make_user('one@example.com')
    _add_purchase(u1, savings_decision='moved')
    u3 = _make_user('three@example.com')
    for _ in range(3):
        _add_purchase(u3, savings_decision='moved')
    # 3 moved purchases earn 3x the bucket vs 1 (same wait band, same ratio bonus)
    assert _score(u3) - _score(u1) == 2 * SCORE_WEIGHTS['savings_bucket']['moved']


def test_decisions_outside_window_do_not_count(app):
    user = _make_user('stale@example.com')
    now = datetime.datetime.now()
    old = WishItem(
        user_id=user.id, name='Old', brand='Acme', category='Tops', price=50.0,
        link='https://example.com/x', purchased=True,
        purchase_date=now - datetime.timedelta(days=120),  # outside 90-day window
        date=now - datetime.timedelta(days=130),
        wish_period=datetime.timedelta(days=10),
        savings_decision='declined',
    )
    db.session.add(old)
    db.session.commit()
    assert compute_shopping_habits_score(user)['has_data'] is False
