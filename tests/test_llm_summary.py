"""Tests for OpenAI website summarization and its authenticated API route."""
import asyncio
from collections.abc import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_jwt_extended import JWTManager, create_access_token
from werkzeug.test import TestResponse

from website import db
from website.api import api
from website.content_parser import ParsedWebsite
from website.llm_summary import JsonObject, OpenAISummarizer, WebsiteSummary


class FakeResponse:
    """Small requests.Response substitute for OpenAI client tests."""

    def __init__(
        self,
        status_code: int,
        payload: JsonObject,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Store the status, JSON payload, and response headers."""
        self.status_code: int = status_code
        self._payload: JsonObject = payload
        self.headers: dict[str, str] = headers or {}

    def json(self) -> JsonObject:
        """Return the configured OpenAI response payload."""
        return self._payload


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    """Create an in-memory API app with JWT support."""
    flask_app: Flask = Flask(__name__)
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    flask_app.config['JWT_SECRET_KEY'] = 'test-secret-for-website-summary-12345'
    db.init_app(flask_app)
    JWTManager(flask_app)
    flask_app.register_blueprint(api, url_prefix='/api/v1')
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Return the website-summary API test client."""
    return app.test_client()


def test_summarizer_retries_transient_server_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A temporary OpenAI server error is retried before returning content."""
    responses: list[FakeResponse] = [
        FakeResponse(503, {}),
        FakeResponse(200, {
            'choices': [{
                'message': {'content': 'A compact tote intended for daily use.'},
            }],
        }),
    ]
    delays: list[float] = []

    def fake_post(
        url: str,
        headers: dict[str, str],
        json: JsonObject,
        timeout: int,
    ) -> FakeResponse:
        """Return the next configured OpenAI response."""
        assert url.endswith('/chat/completions')
        assert headers['Authorization'] == 'Bearer test-key'
        assert json['model'] == 'gpt-4o-mini'
        assert timeout == 30
        return responses.pop(0)

    async def record_sleep(seconds: float) -> None:
        """Record retry delays without slowing the test suite."""
        delays.append(seconds)

    monkeypatch.setattr('website.llm_summary.requests.post', fake_post)
    summarizer: OpenAISummarizer = OpenAISummarizer(
        api_key='test-key',
        base_delay_seconds=0.25,
        sleep=record_sleep,
    )
    page: ParsedWebsite = ParsedWebsite(
        title='Everyday Tote',
        content='A compact canvas tote for daily errands.',
        reviews=(),
    )

    summary: WebsiteSummary = asyncio.run(summarizer.summarize(page))

    assert summary.summary == 'A compact tote intended for daily use.'
    assert summary.review_summary is None
    assert delays == [0.25]
    assert responses == []


def test_authenticated_endpoint_parses_html_and_returns_summary(
    app: Flask,
    client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API connects raw-HTML parsing to the summarization service."""
    class FakeSummarizer:
        """Return deterministic output while exercising route orchestration."""

        async def summarize(self, page: ParsedWebsite) -> WebsiteSummary:
            """Build a summary from parser output without making a network call."""
            return WebsiteSummary(
                title=page.title,
                summary=f'Summary of {page.content}',
                review_summary=None,
                review_count=len(page.reviews),
            )

    monkeypatch.setattr('website.api.OpenAISummarizer', FakeSummarizer)
    with app.app_context():
        token: str = create_access_token(identity='1')

    response: TestResponse = client.post(
        '/api/v1/summarize',
        json={'html': '<html><title>Tote</title><main>Lightweight bag.</main></html>'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        'title': 'Tote',
        'summary': 'Summary of Lightweight bag.',
        'review_summary': None,
        'review_count': 0,
    }
