"""Bulk product-extraction service and API integration tests."""
import asyncio
import threading
import time
from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_jwt_extended import JWTManager, create_access_token

from website import db
from website.api import api
from website.batch_extraction import (
    BatchExtractionError,
    BatchExtractor,
    MAX_BATCH_URLS,
    ScrapedItem,
)
from website.models import User

ResultPayload = dict[str, str | bool | ScrapedItem | None]
BatchPayload = dict[str, int | list[ResultPayload]]


@pytest.fixture
def app() -> Iterator[Flask]:
    """Create an in-memory API app."""
    flask_app: Flask = Flask(__name__)
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    flask_app.config['JWT_SECRET_KEY'] = 'test-secret-with-enough-length-12345'
    db.init_app(flask_app)
    JWTManager(flask_app)
    flask_app.register_blueprint(api, url_prefix='/api/v1')
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Return the API test client."""
    return app.test_client()


def _make_user() -> User:
    """Persist an authenticated API user."""
    user: User = User(
        email='batch@example.com',
        first_name='Batch',
        password='x',
        zipcode='10001',
    )
    db.session.add(user)
    db.session.commit()
    return user


def _token(user: User) -> str:
    """Create a JWT for the supplied user."""
    return create_access_token(identity=str(user.id))


def test_service_isolates_one_scrape_failure() -> None:
    """One failed URL does not abort successful URLs."""
    def fake_scraper(url: str) -> ScrapedItem:
        if 'broken' in url:
            raise RuntimeError('store blocked this request')
        return {'name': url.rsplit('/', 1)[-1], 'image_url': 'https://img.test/x.jpg'}

    extractor: BatchExtractor = BatchExtractor(scraper=fake_scraper)
    results = asyncio.run(extractor.extract([
        'https://shop.test/dress',
        'https://broken.test/item',
    ]))
    by_url: dict[str, ResultPayload] = {
        result.url: result.to_dict() for result in results
    }

    assert by_url['https://shop.test/dress']['success'] is True
    assert by_url['https://broken.test/item']['success'] is False
    assert 'blocked' in str(by_url['https://broken.test/item']['error'])


def test_service_enforces_concurrency_bound() -> None:
    """The semaphore limits simultaneous synchronous scraper calls."""
    lock: threading.Lock = threading.Lock()
    active: int = 0
    max_active: int = 0

    def fake_scraper(url: str) -> ScrapedItem:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return {'name': url, 'image_url': 'https://img.test/x.jpg'}

    extractor: BatchExtractor = BatchExtractor(
        max_concurrency=2,
        scraper=fake_scraper,
    )
    urls: list[str] = [f'https://shop.test/{index}' for index in range(6)]
    results = asyncio.run(extractor.extract(urls))

    assert len(results) == 6
    assert max_active == 2


def test_service_rejects_invalid_url_and_oversized_batch() -> None:
    """Service validation protects non-HTTP input and batch size."""
    extractor: BatchExtractor = BatchExtractor(scraper=lambda url: {'name': url})
    with pytest.raises(BatchExtractionError, match='invalid URL'):
        asyncio.run(extractor.extract(['not-a-url']))

    too_many: list[str] = [
        f'https://shop.test/{index}' for index in range(MAX_BATCH_URLS + 1)
    ]
    with pytest.raises(BatchExtractionError, match='no more than'):
        asyncio.run(extractor.extract(too_many))


def test_batch_endpoint_returns_per_url_results(
        client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The authenticated endpoint exposes successes and failures together."""
    user: User = _make_user()

    def fake_scraper(url: str) -> ScrapedItem:
        if 'broken' in url:
            raise RuntimeError('could not extract product')
        return {
            'name': 'Silk Dress',
            'brand': 'Example',
            'price': 120.0,
            'image_url': 'https://img.test/dress.jpg',
        }

    monkeypatch.setattr('website.batch_extraction.scrape_item', fake_scraper)
    response = client.post(
        '/api/v1/extract/batch',
        json={'urls': [
            'HTTPS://SHOP.TEST/dress#details',
            'https://broken.test/item',
        ]},
        headers={'Authorization': f'Bearer {_token(user)}'},
    )

    assert response.status_code == 200
    payload: BatchPayload = response.get_json()
    assert payload['count'] == 2
    assert payload['succeeded'] == 1
    assert payload['failed'] == 1
    results: list[ResultPayload] = payload['results']
    by_url: dict[str, ResultPayload] = {
        str(result['url']): result for result in results
    }
    assert by_url['https://shop.test/dress']['data']['name'] == 'Silk Dress'
    assert by_url['https://broken.test/item']['success'] is False


def test_batch_endpoint_validates_payload(client: FlaskClient) -> None:
    """Invalid shapes and URLs return clear 400 responses."""
    user: User = _make_user()
    headers: dict[str, str] = {
        'Authorization': f'Bearer {_token(user)}'
    }

    empty = client.post('/api/v1/extract/batch', json={'urls': []}, headers=headers)
    invalid = client.post(
        '/api/v1/extract/batch',
        json={'urls': ['ftp://shop.test/item']},
        headers=headers,
    )
    oversized = client.post(
        '/api/v1/extract/batch',
        json={'urls': [
            f'https://shop.test/{index}' for index in range(MAX_BATCH_URLS + 1)
        ]},
        headers=headers,
    )

    assert empty.status_code == 400
    assert invalid.status_code == 400
    assert oversized.status_code == 400
