"""Behavior tests for the paginated review-crawler client."""
import asyncio

import pytest
import requests

from website.review_crawler import (
    CrawlerResponseError,
    JsonObject,
    JsonValue,
    Review,
    ReviewCrawler,
)


class FakeCrawlerResponse:
    """Small requests.Response substitute for crawler tests."""

    def __init__(self, status_code: int, payload: JsonObject) -> None:
        """Store an HTTP status and crawler JSON payload."""
        self.status_code: int = status_code
        self._payload: JsonObject = payload

    def raise_for_status(self) -> None:
        """Raise the requests error used by the production client."""
        if self.status_code >= 400:
            raise requests.HTTPError(f'HTTP {self.status_code}')

    def json(self) -> JsonObject:
        """Return the configured crawler payload."""
        return self._payload


def test_crawler_normalizes_one_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One valid crawler page becomes typed reviews."""
    calls: list[tuple[str, int]] = []

    def fake_get(url: str, **kwargs: JsonValue) -> FakeCrawlerResponse:
        """Return one deterministic crawler page."""
        assert url == 'https://crawler.test/reviews'
        params_value: JsonValue = kwargs.get('params')
        assert isinstance(params_value, dict)
        target_value: JsonValue = params_value.get('url')
        page_value: JsonValue = params_value.get('page')
        assert isinstance(target_value, str)
        assert type(page_value) is int
        calls.append((target_value, page_value))
        return FakeCrawlerResponse(200, {
            'reviews': [
                {'id': 'r1', 'text': 'Great fabric.', 'rating': 5},
                {'id': 'r2', 'text': 'Runs small.', 'rating': 3},
            ],
            'total_pages': 1,
        })

    monkeypatch.setattr('website.review_crawler.requests.get', fake_get)
    crawler: ReviewCrawler = ReviewCrawler(
        crawler_url='https://crawler.test/reviews'
    )

    reviews: list[Review] = asyncio.run(
        crawler.fetch_reviews('https://shop.test/tote')
    )
    by_id: dict[str, Review] = {review.id: review for review in reviews}

    assert calls == [('https://shop.test/tote', 1)]
    assert by_id == {
        'r1': Review(id='r1', text='Great fabric.', rating=5),
        'r2': Review(id='r2', text='Runs small.', rating=3),
    }


def test_crawler_rejects_malformed_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-list reviews field produces a stable crawler error."""
    def fake_get(url: str, **kwargs: JsonValue) -> FakeCrawlerResponse:
        """Return malformed crawler JSON."""
        return FakeCrawlerResponse(200, {
            'reviews': 'not-a-list',
            'total_pages': 1,
        })

    monkeypatch.setattr('website.review_crawler.requests.get', fake_get)
    crawler: ReviewCrawler = ReviewCrawler(
        crawler_url='https://crawler.test/reviews'
    )

    with pytest.raises(CrawlerResponseError, match='reviews must be a list'):
        asyncio.run(crawler.fetch_reviews('https://shop.test/tote'))
