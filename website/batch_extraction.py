"""Concurrent bulk product extraction for the mobile API.

The existing :func:`website.url_extraction.scrape_item` function is
synchronous and may block on HTTP or Playwright. ``BatchExtractor`` keeps that
well-tested boundary intact while running several independent URLs concurrently
through ``asyncio.to_thread``. A semaphore prevents one request from spawning
an unbounded number of browser/network workers.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from .url_extraction import ItemDetails, scrape_item

MAX_BATCH_URLS = 10
DEFAULT_CONCURRENCY = 4
MAX_CONCURRENCY = 8

ScrapedValue = str | int | float | None
ScrapedItem = dict[str, ScrapedValue]
Scraper = Callable[[str], ScrapedItem]


class BatchExtractionError(ValueError):
    """Raised when batch configuration or a submitted URL is invalid."""


@dataclass(frozen=True)
class ExtractionResult:
    """The success or failure result for one requested URL."""

    url: str
    success: bool
    data: ScrapedItem | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, str | bool | ScrapedItem | None]:
        """Return a JSON-serializable representation for the API response."""
        return {
            'url': self.url,
            'success': self.success,
            'data': self.data,
            'error': self.error,
        }


class BatchExtractor:
    """Extract product metadata from a bounded list of URLs concurrently.

    Results are returned in the same order as the submitted URLs, including
    duplicate URLs. Failures are isolated to their URL and do not abort the
    rest of the batch.
    """

    def __init__(self, max_concurrency: int = DEFAULT_CONCURRENCY,
                 scraper: Scraper | None = None) -> None:
        """Create an extractor with a bounded worker count."""
        if max_concurrency < 1 or max_concurrency > MAX_CONCURRENCY:
            raise BatchExtractionError(
                f'max_concurrency must be between 1 and {MAX_CONCURRENCY}'
            )
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._scraper: Scraper = scraper or scrape_item

    async def extract(self, urls: list[str],
                      enrich_images: bool = False) -> list[ExtractionResult]:
        """Extract every URL and return one result per input URL.

        At most :data:`MAX_BATCH_URLS` URLs may be submitted. Optional image
        enrichment performs a second asynchronous lookup only when the base
        scraper did not return an image.
        """
        if not urls:
            raise BatchExtractionError('urls must contain at least one URL')
        if len(urls) > MAX_BATCH_URLS:
            raise BatchExtractionError(
                f'urls must contain no more than {MAX_BATCH_URLS} entries'
            )

        normalized_urls: list[str] = [self._normalize_url(url) for url in urls]
        tasks: list[asyncio.Task[ExtractionResult]] = [
            asyncio.create_task(self._extract_one(url, enrich_images))
            for url in normalized_urls
        ]
        results: list[ExtractionResult] = []
        for task in asyncio.as_completed(tasks):
            results.append(await task)
        return results

    async def _extract_one(self, url: str,
                           enrich_images: bool) -> ExtractionResult:
        """Run one synchronous scrape in the thread pool and isolate errors."""
        async with self._semaphore:
            try:
                data: ScrapedItem = await asyncio.to_thread(self._scraper, url)
                if enrich_images and not data.get('image_url'):
                    self._enrich_missing_image(data)
                return ExtractionResult(url=url, success=True, data=data)
            except Exception as exc:
                return ExtractionResult(
                    url=url,
                    success=False,
                    error=str(exc) or exc.__class__.__name__,
                )

    async def _enrich_missing_image(self, data: ScrapedItem) -> None:
        """Populate ``image_url`` via the existing Google fallback."""
        brand_value: ScrapedValue = data.get('brand')
        name_value: ScrapedValue = data.get('name')
        description_value: ScrapedValue = data.get('description')
        price_value: ScrapedValue = data.get('price')
        brand: str | None = str(brand_value) if brand_value is not None else None
        name: str | None = str(name_value) if name_value is not None else None
        description: str | None = (
            str(description_value) if description_value is not None else None
        )
        price: str | None = str(price_value) if price_value is not None else None
        image_url: str | None = await asyncio.to_thread(
            ItemDetails.google_search_image_fallback,
            brand,
            name,
            description,
            price,
        )
        data['image_url'] = image_url

    @staticmethod
    def _normalize_url(raw_url: str) -> str:
        """Validate and normalize one public HTTP(S) URL."""
        if not isinstance(raw_url, str):
            raise BatchExtractionError('each URL must be a string')
        candidate: str = raw_url.strip()
        parsed = urlparse(candidate)
        if parsed.scheme.lower() not in ('http', 'https') or not parsed.netloc:
            raise BatchExtractionError(f'invalid URL: {raw_url!r}')
        return urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or '/',
            parsed.params,
            parsed.query,
            '',
        ))
