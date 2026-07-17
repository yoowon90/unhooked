"""Monthly budget summary + API."""
import datetime

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from website import db
from website.api import api
from website.budget import budget_status, month_spend
from website.models import User, WishItem


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'  # in-memory
    app.config['JWT_SECRET_KEY'] = 'test'
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(api, url_prefix='/api/v1')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


def _make_user(budget=500.0):
    user = User(email='t@example.com', first_name='Test', password='x',
                zipcode='10001', monthly_budget=budget)
    db.session.add(user)
    db.session.commit()
    return user


def _add_purchase(user, price, when):
    item = WishItem(
        user_id=user.id, name='Item', brand='Acme', category='Tops',
        link='https://example.com/x',
        price=price, taxed_price=price, total_price=price,
        purchased=True, purchase_date=when,
    )
    db.session.add(item)
    db.session.commit()
    return item


def test_month_spend_sums_this_months_purchases(app):
    user = _make_user()
    this_month = datetime.datetime.now().replace(day=2, hour=12)
    _add_purchase(user, 60.0, this_month)
    _add_purchase(user, 40.0, this_month)
    assert month_spend(user.wishitems, as_of=this_month) == 100.0


def test_budget_status_reports_spent_and_remaining(app):
    user = _make_user(budget=500.0)
    this_month = datetime.datetime.now().replace(day=2, hour=12)
    _add_purchase(user, 200.0, this_month)

    status = budget_status(user, as_of=this_month)
    assert status['budget'] == 500.0
    assert status['spent'] == 200.0
    assert status['remaining'] == 300.0
    assert status['percent_used'] == 40
    assert status['over_budget'] is False


def test_get_budget_endpoint(client):
    user = _make_user(budget=300.0)
    this_month = datetime.datetime.now().replace(day=2, hour=12)
    _add_purchase(user, 150.0, this_month)

    token = create_access_token(identity=str(user.id))
    resp = client.get('/api/v1/reports/budget',
                      headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    assert resp.get_json()['spent'] == 150.0


def test_set_budget_endpoint(client):
    user = _make_user(budget=None)
    token = create_access_token(identity=str(user.id))
    resp = client.put('/api/v1/user/budget', json={'monthly_budget': 750},
                      headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    assert resp.get_json()['budget'] == 750.0
