"""Happy-path integration for the authenticated Realtime session endpoint."""

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_jwt_extended import JWTManager, create_access_token
from werkzeug.test import TestResponse

from website import db
from website.api import api
from website.voice_search import JsonObject


class SearchEndpointResponse:
    """Successful web-search response for route integration."""

    status_code: int = 200

    def json(self) -> JsonObject:
        """Return one assistant message without source annotations."""
        return {
            'output': [{
                'type': 'message',
                'content': [{
                    'type': 'output_text',
                    'text': 'The museum closes at 8 PM.',
                }],
            }],
        }


class SessionResponse:
    """Successful Realtime client-secret response at the HTTP boundary."""

    status_code: int = 200

    def json(self) -> JsonObject:
        """Return one short-lived browser credential."""
        return {
            'value': 'ek_test_realtime_secret',
            'expires_at': 2_000_000_000,
        }


def test_authenticated_user_can_create_session_and_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API mints an ephemeral credential without exposing the server key."""
    def fake_post(
        url: str,
        headers: dict[str, str],
        json: JsonObject,
        timeout: int,
    ) -> SessionResponse | SearchEndpointResponse:
        """Return deterministic responses for both OpenAI endpoints."""
        assert headers['Authorization'] == 'Bearer server-only-key'
        assert timeout == 30
        if url.endswith('/v1/realtime/client_secrets'):
            assert headers['OpenAI-Safety-Identifier'] != '42'
            assert json['session']['tools'][0]['name'] == 'search_web'
            return SessionResponse()
        assert url.endswith('/v1/responses')
        assert json['input'] == 'When does the museum close?'
        return SearchEndpointResponse()

    monkeypatch.setenv('OPENAI_API_KEY', 'server-only-key')
    monkeypatch.setattr('website.voice_search.requests.post', fake_post)

    flask_app: Flask = Flask(__name__)
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    flask_app.config['JWT_SECRET_KEY'] = 'test-secret-for-realtime-voice-12345'
    db.init_app(flask_app)
    JWTManager(flask_app)
    flask_app.register_blueprint(api, url_prefix='/api/v1')
    with flask_app.app_context():
        db.create_all()
        token: str = create_access_token(identity='42')
        client: FlaskClient = flask_app.test_client()
        response: TestResponse = client.post(
            '/api/v1/voice/session',
            headers={'Authorization': f'Bearer {token}'},
        )
        search_response: TestResponse = client.post(
            '/api/v1/voice/search',
            json={
                'call_id': 'call-api-1',
                'query': 'When does the museum close?',
            },
            headers={'Authorization': f'Bearer {token}'},
        )
        db.session.remove()

    assert response.status_code == 200
    assert response.get_json() == {
        'value': 'ek_test_realtime_secret',
        'expires_at': 2_000_000_000,
    }
    assert search_response.status_code == 200
    search_payload: JsonObject = search_response.get_json()
    assert search_payload['answer'] == 'The museum closes at 8 PM.'
    assert search_payload['sources'] == []
    assert search_payload['events'][1] == {'type': 'response.create'}
