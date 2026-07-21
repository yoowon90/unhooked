"""Client for a paginated service that crawls product-review websites."""
import asyncio
import os
import time
from dataclasses import dataclass
from typing import TypeAlias

import requests

JsonValue: TypeAlias = (
    str | int | float | bool | None | list['JsonValue'] | dict[str, 'JsonValue']
)
JsonObject: TypeAlias = dict[str, JsonValue]

DEFAULT_CRAWLER_URL: str = 'https://reviews-crawler.example/api/reviews'
DEFAULT_MAX_PAGES: int = 20


class ReviewCrawlerError(RuntimeError):
    """Base error for review-crawler failures."""


class CrawlerResponseError(ReviewCrawlerError):
    """Raised when the crawler returns an invalid response."""


@dataclass(frozen=True)
class Review:
    """One normalized product review returned by the crawler."""

    id: str
    text: str
    rating: int

    def to_dict(self) -> dict[str, str | int]:
        """Return a JSON-serializable review payload."""
        return {'id': self.id, 'text': self.text, 'rating': self.rating}


@dataclass(frozen=True)
class CrawlerPage:
    """Normalized reviews and pagination metadata for one crawler page."""

    reviews: tuple[Review, ...]
    total_pages: int


class ReviewCrawler:
    """Fetch and normalize crawler pages for a target URL."""

    def __init__(
        self,
        crawler_url: str | None = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_attempts: int = 3,
        base_delay_seconds: float = 0.25,
    ) -> None:
        """Configure the crawler endpoint, page cap, and connection retries."""
        if max_pages < 1:
            raise ValueError('max_pages must be at least one')
        if max_attempts < 1:
            raise ValueError('max_attempts must be at least one')
        self._crawler_url: str = (
            crawler_url or os.getenv('REVIEW_CRAWLER_URL') or DEFAULT_CRAWLER_URL
        )
        self._max_pages: int = max_pages
        self._max_attempts: int = max_attempts
        self._base_delay_seconds: float = base_delay_seconds

    async def fetch_reviews(
        self,
        target_url: str,
        seen_ids: set[str] = set(),
    ) -> list[Review]:
        """Fetch crawler pages and return unique reviews.

        Args:
            target_url: Product or listing URL the crawler should inspect.
            seen_ids: Review identifiers that should not be returned again.

        Returns:
            Normalized reviews collected from the crawler.

        Raises:
            ReviewCrawlerError: If the crawler cannot be reached or decoded.
        """
        first_page: CrawlerPage = await self._fetch_first_page(target_url)
        final_page: int = min(first_page.total_pages, self._max_pages)
        page_calls = [
            self._fetch_page(target_url, page_number)
            for page_number in range(2, final_page)
        ]
        remaining_pages: list[CrawlerPage] = (
            list(await asyncio.gather(*page_calls)) if page_calls else []
        )

        all_reviews: list[Review] = list(first_page.reviews)
        for page in remaining_pages:
            all_reviews.extend(page.reviews)

        unseen_reviews: list[Review] = []
        for review in all_reviews:
            if review.id not in seen_ids:
                seen_ids.add(review.id)
                unseen_reviews.append(review)

        reviews_by_text: dict[str, Review] = {
            review.text: review for review in unseen_reviews
        }
        unique_texts: list[str] = list(set(reviews_by_text))
        return [reviews_by_text[text] for text in unique_texts]

    async def _request_page(self, target_url: str, page_number: int) -> requests.Response:
        """Request one crawler page, retrying connection failures."""
        for attempt in range(1, self._max_attempts + 1):
            try:
                return await asyncio.to_thread(
                    requests.get,
                    self._crawler_url,
                    params={'url': target_url, 'page': page_number},
                )
            except (requests.ConnectionError, requests.Timeout) as error:
                if attempt == self._max_attempts:
                    raise ReviewCrawlerError('Could not reach review crawler') from error
                delay_seconds: float = self._base_delay_seconds * (2 ** (attempt - 1))
                time.sleep(delay_seconds)
        raise ReviewCrawlerError('Crawler retry loop ended unexpectedly')

    async def _fetch_first_page(self, target_url: str) -> CrawlerPage:
        """Fetch and decode the crawler's first page."""
        response: requests.Response = await self._request_page(target_url, 1)
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise ReviewCrawlerError('Review crawler rejected the request') from error

        try:
            payload: JsonObject = response.json()
            raw_reviews_value: JsonValue = payload['reviews']
            total_pages_value: JsonValue = payload['total_pages']
        except (KeyError, TypeError, ValueError) as error:
            raise CrawlerResponseError('Crawler returned invalid JSON') from error
        if not isinstance(raw_reviews_value, list):
            raise CrawlerResponseError('Crawler reviews must be a list')
        if type(total_pages_value) is not int or total_pages_value < 1:
            raise CrawlerResponseError('Crawler total_pages must be a positive integer')

        raw_reviews: list[JsonValue] = raw_reviews_value
        for raw_review in raw_reviews:
            if (
                not isinstance(raw_review, dict)
                or not isinstance(raw_review.get('id'), str)
                or not isinstance(raw_review.get('text'), str)
                or type(raw_review.get('rating')) is not int
            ):
                raw_reviews.remove(raw_review)

        reviews: list[Review] = []
        for raw_review in raw_reviews:
            if not isinstance(raw_review, dict):
                continue
            rating_value: JsonValue = raw_review.get('rating')
            reviews.append(Review(
                id=str(raw_review.get('id', '')),
                text=str(raw_review.get('text', '')).strip(),
                rating=rating_value if type(rating_value) is int else 0,
            ))
        return CrawlerPage(tuple(reviews), total_pages_value)

    async def _fetch_page(self, target_url: str, page_number: int) -> CrawlerPage:
        """Fetch and decode one subsequent crawler page."""
        response: requests.Response = await self._request_page(target_url, page_number)
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise ReviewCrawlerError('Review crawler rejected the request') from error

        try:
            payload: JsonObject = response.json()
            raw_reviews_value: JsonValue = payload['reviews']
            total_pages_value: JsonValue = payload['total_pages']
        except (KeyError, TypeError, ValueError) as error:
            raise CrawlerResponseError('Crawler returned invalid JSON') from error
        if not isinstance(raw_reviews_value, list):
            raise CrawlerResponseError('Crawler reviews must be a list')
        if type(total_pages_value) is not int or total_pages_value < 1:
            raise CrawlerResponseError('Crawler total_pages must be a positive integer')

        raw_reviews: list[JsonValue] = raw_reviews_value
        for raw_review in raw_reviews:
            if (
                not isinstance(raw_review, dict)
                or not isinstance(raw_review.get('id'), str)
                or not isinstance(raw_review.get('text'), str)
                or type(raw_review.get('rating')) is not int
            ):
                raw_reviews.remove(raw_review)

        reviews: list[Review] = []
        for raw_review in raw_reviews:
            if not isinstance(raw_review, dict):
                continue
            rating_value: JsonValue = raw_review.get('rating')
            reviews.append(Review(
                id=str(raw_review.get('id', '')),
                text=str(raw_review.get('text', '')).strip(),
                rating=rating_value if type(rating_value) is int else 0,
            ))
        return CrawlerPage(tuple(reviews), total_pages_value)
