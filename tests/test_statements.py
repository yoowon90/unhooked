"""Integration tests for the ledger statement API."""
import datetime
from collections.abc import Generator
from typing import cast

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_jwt_extended import JWTManager, create_access_token
from werkzeug.test import TestResponse

from website import db, ledger
from website.api import api
from website.models import LedgerTransaction, User
from website.statements import StatementPayload


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    """Create an in-memory app with the savings feature enabled."""
    flask_app: Flask = Flask(__name__)
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    flask_app.config['JWT_SECRET_KEY'] = 'test-secret-key-for-ledger-statements-12345'
    flask_app.config['SAVINGS_FEATURE_ENABLED'] = True
    db.init_app(flask_app)
    JWTManager(flask_app)
    flask_app.register_blueprint(api, url_prefix='/api/v1')
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Return the app test client."""
    return app.test_client()


@pytest.fixture
def user(app: Flask) -> User:
    """Create one authenticated statement owner."""
    statement_user: User = User(
        email='statement@example.com',
        first_name='Statement',
        password='x',
        zipcode='10001',
    )
    db.session.add(statement_user)
    db.session.commit()
    return statement_user


def _token(user: User) -> str:
    """Create a JWT for the fixture user."""
    return create_access_token(identity=str(user.id))


def _post_transfer(user: User, amount_cents: int, created_at: datetime.datetime) -> LedgerTransaction:
    """Post one savings transfer and place it at a deterministic timestamp."""
    transaction: LedgerTransaction = ledger.transfer_to_savings(user.id, amount_cents)
    transaction.created_at = created_at
    db.session.commit()
    return transaction


def test_statement_returns_period_balances_and_lines(client: FlaskClient, user: User) -> None:
    """A normal savings statement includes opening balance and period activity."""
    _post_transfer(user, 1000, datetime.datetime(2026, 1, 5, 9, 0))
    period_transaction: LedgerTransaction = _post_transfer(
        user,
        2500,
        datetime.datetime(2026, 1, 15, 12, 30),
    )
    headers: dict[str, str] = {'Authorization': f'Bearer {_token(user)}'}

    response: TestResponse = client.get(
        '/api/v1/ledger/statement',
        query_string={
            'account': 'savings',
            'start_date': '2026-01-10',
            'end_date': '2026-02-01',
        },
        headers=headers,
    )

    assert response.status_code == 200
    payload: StatementPayload = cast(StatementPayload, response.get_json())
    assert payload['account'] == 'savings'
    assert payload['opening_balance_cents'] == 1000
    assert payload['closing_balance_cents'] == 3500
    assert payload['net_change_cents'] == 2500
    assert payload['transaction_count'] == 1
    assert payload['average_amount'] == '$25.00'
    assert payload['saved_cents'] == 2500
    assert payload['line_items'] == [{
        'transaction_id': period_transaction.id,
        'amount_cents': 2500,
        'status': 'pending',
        'memo': 'Savings match',
        'created_at': period_transaction.created_at.isoformat(),
    }]


@pytest.mark.parametrize(
    'query_string,error',
    [
        (
            {'account': 'cash', 'start_date': '2026-01-01', 'end_date': '2026-02-01'},
            'account must be checking or savings',
        ),
        (
            {'account': 'savings', 'start_date': 'not-a-date', 'end_date': '2026-02-01'},
            'start_date and end_date required in YYYY-MM-DD format',
        ),
        (
            {'account': 'savings', 'start_date': '2026-02-01', 'end_date': '2026-01-01'},
            'start_date must be before end_date',
        ),
    ],
)
def test_statement_rejects_invalid_requests(
    client: FlaskClient,
    user: User,
    query_string: dict[str, str],
    error: str,
) -> None:
    """Invalid account/date inputs return a useful client error."""
    headers: dict[str, str] = {'Authorization': f'Bearer {_token(user)}'}
    response: TestResponse = client.get(
        '/api/v1/ledger/statement',
        query_string=query_string,
        headers=headers,
    )
    assert response.status_code == 400
    assert response.get_json() == {'error': error}


def test_statement_is_hidden_when_savings_feature_is_disabled(
    app: Flask,
    client: FlaskClient,
    user: User,
) -> None:
    """Production-style apps keep the dev-only statement endpoint unavailable."""
    app.config['SAVINGS_FEATURE_ENABLED'] = False
    headers: dict[str, str] = {'Authorization': f'Bearer {_token(user)}'}
    response: TestResponse = client.get(
        '/api/v1/ledger/statement',
        query_string={
            'account': 'savings',
            'start_date': '2026-01-01',
            'end_date': '2026-02-01',
        },
        headers=headers,
    )
    assert response.status_code == 404
