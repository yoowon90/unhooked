"""Plaid rail-bridge tests. plaid_client is monkeypatched — no network.

The real-sandbox path is exercised separately by scripts/smoke; these tests
pin the *contract*: what gets stored, what happens on decline/error, and
that rail failures never corrupt the ledger.
"""
import pytest
from cryptography.fernet import Fernet
from flask import Flask

from website import db
from website import ledger
from website import transfers
from website.crypto import encrypt_token, decrypt_token, CryptoError
from website.models import User, LedgerAccount
from website.plaid_client import PlaidError


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('TOKEN_ENCRYPTION_KEY', Fernet.generate_key().decode())
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


@pytest.fixture
def linked_user(user, monkeypatch):
    """User with a connected sandbox bank (mocked Plaid)."""
    monkeypatch.setattr(transfers.plaid_client, 'exchange_public_token',
                        lambda pt: {'access_token': 'access-sandbox-123', 'item_id': 'item-1'})
    monkeypatch.setattr(transfers.plaid_client, 'get_institution_name',
                        lambda at: 'First Platypus Bank')
    monkeypatch.setattr(transfers.plaid_client, 'get_accounts', lambda at: [
        {'account_id': 'acct-chk', 'name': 'Plaid Checking', 'subtype': 'checking', 'mask': '0000'},
        {'account_id': 'acct-sav', 'name': 'Plaid Saving', 'subtype': 'savings', 'mask': '1111'},
    ])
    transfers.connect_bank(user, 'public-sandbox-token')
    return user


# ── crypto ────────────────────────────────────────────────────────────────────

def test_encrypt_roundtrip(app):
    ct = encrypt_token('access-sandbox-secret')
    assert ct != 'access-sandbox-secret'
    assert decrypt_token(ct) == 'access-sandbox-secret'
    assert encrypt_token(None) is None and decrypt_token(None) is None


def test_decrypt_with_wrong_key_raises(app, monkeypatch):
    ct = encrypt_token('secret')
    monkeypatch.setenv('TOKEN_ENCRYPTION_KEY', Fernet.generate_key().decode())
    with pytest.raises(CryptoError):
        decrypt_token(ct)


# ── connect / disconnect ──────────────────────────────────────────────────────

def test_connect_bank_stores_encrypted_and_maps_accounts(linked_user):
    assert linked_user.plaid_access_token_enc is not None
    assert 'access-sandbox-123' not in linked_user.plaid_access_token_enc  # never plaintext
    assert decrypt_token(linked_user.plaid_access_token_enc) == 'access-sandbox-123'
    assert linked_user.plaid_institution_name == 'First Platypus Bank'

    accounts = {a.kind: a for a in LedgerAccount.query.filter_by(user_id=linked_user.id)}
    assert accounts['checking'].provider_account_id == 'acct-chk'
    assert accounts['savings'].provider_account_id == 'acct-sav'
    assert transfers.bank_connected(linked_user)


def test_disconnect_clears_link_but_keeps_ledger(linked_user, monkeypatch):
    monkeypatch.setattr(transfers.plaid_client, 'remove_item', lambda at: None)
    txn = ledger.transfer_to_savings(linked_user.id, 5000)
    transfers.disconnect_bank(linked_user)

    assert linked_user.plaid_access_token_enc is None
    assert not transfers.bank_connected(linked_user)
    for a in LedgerAccount.query.filter_by(user_id=linked_user.id):
        assert a.provider_account_id is None
    # ledger history untouched
    accounts = ledger.get_or_create_accounts(linked_user.id)
    assert ledger.account_balance_cents(accounts['savings'].id) == 5000
    assert txn.status == 'pending'


# ── origination ───────────────────────────────────────────────────────────────

def test_originate_success_stamps_provider_transfer_id(linked_user, monkeypatch):
    captured = {}

    def fake_auth(access_token, account_id, amount, legal_name, idempotency_key=None):
        captured.update(access_token=access_token, account_id=account_id,
                        amount=amount, idempotency_key=idempotency_key)
        return {'id': 'auth-1', 'decision': 'approved'}

    monkeypatch.setattr(transfers.plaid_client, 'create_transfer_authorization', fake_auth)
    monkeypatch.setattr(transfers.plaid_client, 'create_transfer',
                        lambda at, acct, auth_id, description: {'id': 'transfer-1'})

    txn = ledger.transfer_to_savings(linked_user.id, 6500)
    result = transfers.originate_savings_transfer(linked_user, txn)

    assert result == {'originated': True, 'transfer_id': 'transfer-1'}
    assert txn.provider_transfer_id == 'transfer-1'
    assert captured['access_token'] == 'access-sandbox-123'  # decrypted for the call
    assert captured['account_id'] == 'acct-chk'              # debit leg pulls from checking
    assert captured['amount'] == '65.00'                     # decimal string, from cents
    expected_key = f'unhooked-txn-{txn.id}-{int(txn.created_at.timestamp())}'
    assert captured['idempotency_key'] == expected_key  # retry-safe, id-reuse-proof


def test_originate_declined_keeps_txn_pending_without_provider_id(linked_user, monkeypatch):
    monkeypatch.setattr(transfers.plaid_client, 'create_transfer_authorization',
                        lambda *a, **k: {'id': 'auth-2', 'decision': 'declined',
                                         'decision_rationale': {'description': 'NSF'}})
    txn = ledger.transfer_to_savings(linked_user.id, 9_999_999)
    result = transfers.originate_savings_transfer(linked_user, txn)

    assert result['originated'] is False and result['reason'] == 'declined'
    assert 'NSF' in result['detail']
    assert txn.provider_transfer_id is None
    assert txn.status == 'pending'  # ledger intent survives the rail decline


def test_originate_plaid_error_never_raises(linked_user, monkeypatch):
    def boom(*a, **k):
        raise PlaidError('/transfer/authorization/create',
                         {'error_code': 'INVALID_PRODUCT', 'error_message': 'not enabled'})
    monkeypatch.setattr(transfers.plaid_client, 'create_transfer_authorization', boom)
    txn = ledger.transfer_to_savings(linked_user.id, 1000)
    result = transfers.originate_savings_transfer(linked_user, txn)

    assert result['originated'] is False and result['reason'] == 'error'
    assert 'INVALID_PRODUCT' in result['detail']
    assert txn.provider_transfer_id is None


def test_originate_without_bank_is_a_clean_noop(user):
    txn = ledger.transfer_to_savings(user.id, 1000)
    result = transfers.originate_savings_transfer(user, txn)
    assert result['originated'] is False and result['reason'] == 'not_connected'
    assert txn.status == 'pending'


# ── auto-origination of stuck transactions ────────────────────────────────────

def test_connect_bank_originates_prior_decisions(user, monkeypatch):
    """A 'Yes' recorded before any bank existed is a standing instruction —
    linking a bank fulfills it without asking again."""
    stuck = ledger.transfer_to_savings(user.id, 3000)
    assert stuck.provider_transfer_id is None

    monkeypatch.setattr(transfers.plaid_client, 'exchange_public_token',
                        lambda pt: {'access_token': 'access-sandbox-123', 'item_id': 'item-1'})
    monkeypatch.setattr(transfers.plaid_client, 'get_institution_name', lambda at: 'Bank')
    monkeypatch.setattr(transfers.plaid_client, 'get_accounts', lambda at: [
        {'account_id': 'acct-chk', 'name': 'Checking', 'subtype': 'checking', 'mask': '0000'},
        {'account_id': 'acct-sav', 'name': 'Saving', 'subtype': 'savings', 'mask': '1111'},
    ])
    monkeypatch.setattr(transfers.plaid_client, 'create_transfer_authorization',
                        lambda *a, **k: {'id': 'auth-1', 'decision': 'approved'})
    monkeypatch.setattr(transfers.plaid_client, 'create_transfer',
                        lambda *a, **k: {'id': 'transfer-auto'})

    transfers.connect_bank(user, 'public-token')
    assert stuck.provider_transfer_id == 'transfer-auto'


def test_originate_pending_transfers_skips_done_and_collects_failures(linked_user, monkeypatch):
    done = ledger.transfer_to_savings(linked_user.id, 1000)
    done.provider_transfer_id = 'already-originated'
    settled = ledger.transfer_to_savings(linked_user.id, 1000)
    ledger.settle_transaction(settled)
    nsf = ledger.transfer_to_savings(linked_user.id, 17800)
    ok = ledger.transfer_to_savings(linked_user.id, 2500)
    db.session.commit()

    def auth_by_amount(access_token, account_id, amount, legal_name, idempotency_key=None):
        if amount == '178.00':
            return {'id': 'auth-nsf', 'decision': 'declined',
                    'decision_rationale': {'description': 'insufficient funds'}}
        return {'id': 'auth-ok', 'decision': 'approved'}

    monkeypatch.setattr(transfers.plaid_client, 'create_transfer_authorization', auth_by_amount)
    monkeypatch.setattr(transfers.plaid_client, 'create_transfer',
                        lambda *a, **k: {'id': 'transfer-new'})

    summary = transfers.originate_pending_transfers(linked_user)
    assert summary['originated'] == 1
    assert len(summary['failures']) == 1 and 'insufficient funds' in summary['failures'][0]
    assert ok.provider_transfer_id == 'transfer-new'
    assert nsf.provider_transfer_id is None          # decline: intent survives, retryable
    assert done.provider_transfer_id == 'already-originated'  # untouched


def test_originate_pending_transfers_without_bank_is_noop(user):
    ledger.transfer_to_savings(user.id, 1000)
    summary = transfers.originate_pending_transfers(user)
    assert summary == {'originated': 0, 'skipped': 0, 'failures': []}
