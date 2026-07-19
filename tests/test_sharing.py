"""Shareable wishlist links + public view."""
import datetime

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from website import db
from website.api import api
from website.models import User, WishItem, ShareLink


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


def _make_user(email='t@example.com'):
    user = User(email=email, first_name='Test', password='x', zipcode='10001')
    db.session.add(user)
    db.session.commit()
    return user


def _add_wishlist_item(user, price):
    item = WishItem(
        user_id=user.id, name='Item', brand='Acme', category='Tops',
        link='https://example.com/x', price=price,
        date=datetime.datetime.now(),
    )
    db.session.add(item)
    db.session.commit()
    return item


def _auth(user):
    return {'Authorization': f'Bearer {create_access_token(identity=str(user.id))}'}


def test_create_and_view_share(client):
    user = _make_user()
    _add_wishlist_item(user, 50.0)
    _add_wishlist_item(user, 200.0)

    resp = client.post('/api/v1/share', json={}, headers=_auth(user))
    assert resp.status_code == 201
    token = resp.get_json()['token']

    view = client.get(f'/api/v1/shared/{token}')
    assert view.status_code == 200
    body = view.get_json()
    assert len(body['items']) == 2
    # 50 is under the $110 NYC clothing exemption; 200 is taxed at 8.75%.
    assert body['estimated_total'] == round(50 + 200 * 1.0875, 2)


def test_view_unknown_token_404(client):
    resp = client.get('/api/v1/shared/nope123')
    assert resp.status_code == 404


def test_revoke_share(client):
    user = _make_user()
    resp = client.post('/api/v1/share', json={}, headers=_auth(user))
    token = resp.get_json()['token']

    revoke = client.delete(f'/api/v1/share/{token}', headers=_auth(user))
    assert revoke.status_code == 200
    assert ShareLink.query.filter_by(token=token).first().revoked is True
