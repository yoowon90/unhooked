"""Behavior tests for endpoint-aware Plaid retries without network calls."""
import pytest

from website import plaid_client
from website.plaid_client import JsonObject, PlaidError
from website.plaid_retry import PlaidRetry, RetryConfig


def _no_sleep(_seconds: float) -> None:
    """Replace sleeping in retry behavior tests."""


def _test_retry() -> PlaidRetry:
    """Return a deterministic retry runner for tests."""
    return PlaidRetry(
        RetryConfig(
            max_attempts=3,
            base_delay_seconds=0.5,
            multiplier=2.0,
            max_delay_seconds=4.0,
        ),
        sleep=_no_sleep,
    )


def _transient_error(endpoint: str) -> PlaidError:
    """Build a retryable Plaid response error."""
    return PlaidError(endpoint, {
        'error_code': 'RATE_LIMIT',
        'error_message': 'try again',
    })


def test_delay_grows_exponentially_and_caps() -> None:
    retry: PlaidRetry = _test_retry()
    assert retry.delay_seconds(1) == 0.5
    assert retry.delay_seconds(2) == 1.0
    assert retry.delay_seconds(5) == 4.0


def test_read_endpoint_retries_transient_plaid_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    def flaky_post(endpoint: str, payload: JsonObject) -> JsonObject:
        attempts.append(1)
        if len(attempts) == 1:
            raise _transient_error(endpoint)
        return {'accounts': []}

    monkeypatch.setattr(plaid_client, '_post_once', flaky_post)
    monkeypatch.setattr(plaid_client, '_retry', _test_retry())

    result: JsonObject = plaid_client._post('/accounts/get', {'access_token': 'x'})

    assert result == {'accounts': []}
    assert len(attempts) == 2


def test_idempotent_authorization_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    def flaky_post(endpoint: str, payload: JsonObject) -> JsonObject:
        attempts.append(1)
        if len(attempts) == 1:
            raise _transient_error(endpoint)
        return {'authorization': {'id': 'auth-1', 'decision': 'approved'}}

    monkeypatch.setattr(plaid_client, '_post_once', flaky_post)
    monkeypatch.setattr(plaid_client, '_retry', _test_retry())

    result: JsonObject = plaid_client._post(
        '/transfer/authorization/create',
        {'idempotency_key': 'txn-1'},
    )

    assert result['authorization'] == {'id': 'auth-1', 'decision': 'approved'}
    assert len(attempts) == 2


def test_authorization_without_idempotency_key_does_not_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    def failing_post(endpoint: str, payload: JsonObject) -> JsonObject:
        attempts.append(1)
        raise _transient_error(endpoint)

    monkeypatch.setattr(plaid_client, '_post_once', failing_post)
    monkeypatch.setattr(plaid_client, '_retry', _test_retry())

    with pytest.raises(PlaidError):
        plaid_client._post('/transfer/authorization/create', {})

    assert len(attempts) == 1


def test_transfer_creation_never_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    def failing_post(endpoint: str, payload: JsonObject) -> JsonObject:
        attempts.append(1)
        raise _transient_error(endpoint)

    monkeypatch.setattr(plaid_client, '_post_once', failing_post)
    monkeypatch.setattr(plaid_client, '_retry', _test_retry())

    with pytest.raises(PlaidError):
        plaid_client._post('/transfer/create', {'authorization_id': 'auth-1'})

    assert len(attempts) == 1


def test_permanent_error_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    def failing_post(endpoint: str, payload: JsonObject) -> JsonObject:
        attempts.append(1)
        raise PlaidError(endpoint, {
            'error_code': 'INVALID_INPUT',
            'error_message': 'bad request',
        })

    monkeypatch.setattr(plaid_client, '_post_once', failing_post)
    monkeypatch.setattr(plaid_client, '_retry', _test_retry())

    with pytest.raises(PlaidError):
        plaid_client._post('/transfer/event/sync', {'after_id': 0})

    assert len(attempts) == 1
