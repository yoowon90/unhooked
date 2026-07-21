"""Tests for batched OpenAI categorization and its authenticated API route."""
import asyncio
from collections.abc import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_jwt_extended import JWTManager, create_access_token
from werkzeug.test import TestResponse

from website import db
from website.api import api
from website.review_categorizer import (
    OpenAIReviewCategorizer,
    ReviewCategorization,
)
from website.review_crawler import JsonObject, JsonValue, Review


class FakeCrawlerResponse:
    """Successful crawler response used by the API integration test."""

    def __init__(self, payload: JsonObject) -> None:
        """Store one crawler JSON payload."""
        self.status_code: int = 200
        self._payload: JsonObject = payload

    def raise_for_status(self) -> None:
        """Accept the successful crawler status."""

    def json(self) -> JsonObject:
        """Return the configured crawler payload."""
        return self._payload


class FakeOpenAIResponse:
    """Small requests.Response substitute for categorizer tests."""

    def __init__(self, labels: list[str]) -> None:
        """Build a successful chat-completions response for ordered labels."""
        self.status_code: int = 200
        self._payload: JsonObject = {
            'choices': [{
                'message': {
                    'content': '{"categories": ['
                    + ', '.join(f'"{label}"' for label in labels)
                    + ']}',
                },
            }],
        }

    def json(self) -> JsonObject:
        """Return the configured OpenAI payload."""
        return self._payload


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    """Create an in-memory API app with JWT support."""
    flask_app: Flask = Flask(__name__)
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    flask_app.config['JWT_SECRET_KEY'] = 'test-secret-for-review-categories-12345'
    db.init_app(flask_app)
    JWTManager(flask_app)
    flask_app.register_blueprint(api, url_prefix='/api/v1')
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Return the review-categorization API client."""
    return app.test_client()


def test_categorizer_processes_two_complete_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exactly-sized batches are categorized and combined."""
    responses: list[FakeOpenAIResponse] = [
        FakeOpenAIResponse(['quality', 'quality']),
        FakeOpenAIResponse(['fit', 'shipping']),
    ]
    requested_batches: list[JsonObject] = []

    def fake_post(
        url: str,
        headers: dict[str, str],
        json: JsonObject,
        timeout: int,
    ) -> FakeOpenAIResponse:
        """Return one ordered category response per batch."""
        assert url.endswith('/chat/completions')
        assert headers['Authorization'] == 'Bearer test-key'
        assert timeout == 30
        requested_batches.append(json)
        return responses.pop(0)

    monkeypatch.setattr('website.review_categorizer.requests.post', fake_post)
    reviews: list[Review] = [
        Review(id='r1', text='Excellent material.', rating=5),
        Review(id='r2', text='Feels durable.', rating=5),
        Review(id='r3', text='Runs one size small.', rating=3),
        Review(id='r4', text='Arrived late.', rating=2),
    ]
    categorizer: OpenAIReviewCategorizer = OpenAIReviewCategorizer(
        api_key='test-key',
        batch_size=2,
    )

    result: ReviewCategorization = asyncio.run(
        categorizer.categorize_reviews(reviews)
    )
    payload: dict[str, JsonValue] = result.to_dict()

    assert len(requested_batches) == 2
    assert payload['review_count'] == 4
    assert payload['counts'] == {'quality': 2, 'fit': 1, 'shipping': 1}


def test_authenticated_endpoint_returns_categorized_reviews(
    app: Flask,
    client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API connects crawler output to OpenAI categorization."""
    crawler_reviews: list[JsonValue] = [
        {'id': f'api-{index}', 'text': f'Useful review {index}.', 'rating': 4}
        for index in range(10)
    ]

    def fake_get(url: str, **kwargs: JsonValue) -> FakeCrawlerResponse:
        """Return one full crawler page for the submitted product URL."""
        assert url.endswith('/api/reviews')
        params_value: JsonValue = kwargs.get('params')
        assert isinstance(params_value, dict)
        assert params_value['url'] == 'https://shop.test/tote'
        return FakeCrawlerResponse({
            'reviews': crawler_reviews,
            'total_pages': 1,
        })

    def fake_post(
        url: str,
        headers: dict[str, str],
        json: JsonObject,
        timeout: int,
    ) -> FakeOpenAIResponse:
        """Categorize every review in the complete batch as quality feedback."""
        assert url.endswith('/chat/completions')
        assert headers['Authorization'] == 'Bearer test-key'
        assert timeout == 30
        return FakeOpenAIResponse(['quality'] * 10)

    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setattr('website.review_crawler.requests.get', fake_get)
    monkeypatch.setattr('website.review_categorizer.requests.post', fake_post)
    with app.app_context():
        token: str = create_access_token(identity='1')

    response: TestResponse = client.post(
        '/api/v1/reviews/categorize',
        json={'url': 'https://shop.test/tote'},
        headers={'Authorization': f'Bearer {token}'},
    )

    payload: dict[str, JsonValue] = response.get_json()
    assert response.status_code == 200
    assert payload['url'] == 'https://shop.test/tote'
    assert payload['review_count'] == 10
    assert payload['counts'] == {'quality': 10}


def test_endpoint_requires_authentication(client: FlaskClient) -> None:
    """Unauthenticated callers cannot trigger crawler or OpenAI work."""
    response: TestResponse = client.post(
        '/api/v1/reviews/categorize',
        json={'url': 'https://shop.test/tote'},
    )

    assert response.status_code == 401


def test_endpoint_rejects_non_http_url(
    app: Flask,
    client: FlaskClient,
) -> None:
    """Unsupported target URL schemes fail before external work begins."""
    with app.app_context():
        token: str = create_access_token(identity='1')

    response: TestResponse = client.post(
        '/api/v1/reviews/categorize',
        json={'url': 'file:///tmp/reviews.html'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        'error': 'url must be an absolute HTTP or HTTPS URL',
    }
