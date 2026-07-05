"""Report date-range filtering — items decided ON the end date must count.

Regression test for the same-day boundary bug: end dates parsed at midnight
excluded anything purchased/unhooked later that day.
"""
import datetime

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from website import db
from website.api import api
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


def _make_user():
    user = User(email='t@example.com', first_name='Test', password='x', zipcode='10001')
    db.session.add(user)
    db.session.commit()
    return user


def _add_item(user, **kwargs):
    item = WishItem(
        user_id=user.id,
        name='Item', brand='Acme', category='Tops', price=50.0,
        link='https://example.com/x',
        date=datetime.datetime.now() - datetime.timedelta(days=30),
        **kwargs,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _generate(client, user, start, end):
    token = create_access_token(identity=str(user.id))
    resp = client.post(
        '/api/v1/reports/generate',
        json={'start_date': start, 'end_date': end},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert resp.status_code == 200
    return resp.get_json()


def test_unhooked_on_end_date_is_counted(client):
    user = _make_user()
    today = datetime.date.today()
    _add_item(user, unhooked=True,
              unhooked_date=datetime.datetime.combine(today, datetime.time(14, 32)))
    _add_item(user, purchased=True, taxed_price=54.38,
              purchase_date=datetime.datetime.combine(today, datetime.time(9, 5)))

    report = _generate(client, user,
                       (today - datetime.timedelta(days=7)).isoformat(),
                       today.isoformat())

    assert report['total_saved'] == 50.0
    assert sum(c['count'] for c in report['unhooked_by_category']) == 1
    assert sum(c['count'] for c in report['purchased_by_category']) == 1


def test_decisions_after_end_date_are_excluded(client):
    user = _make_user()
    today = datetime.date.today()
    _add_item(user, unhooked=True,
              unhooked_date=datetime.datetime.combine(today, datetime.time(14, 32)))

    report = _generate(client, user,
                       (today - datetime.timedelta(days=7)).isoformat(),
                       (today - datetime.timedelta(days=1)).isoformat())

    assert report['total_saved'] == 0
    assert report['unhooked_by_category'] == []
