"""Extract concise, LLM-ready content and reviews from raw website HTML."""
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

MAX_HTML_CHARS: int = 250_000
MAX_CONTENT_CHARS: int = 12_000
MAX_REVIEW_CHARS: int = 1_000
MAX_REVIEWS: int = 20


class HtmlParsingError(ValueError):
    """Raised when submitted HTML has no meaningful page content."""


@dataclass(frozen=True)
class ParsedWebsite:
    """Normalized website text ready for summarization."""

    title: str
    content: str
    reviews: tuple[str, ...]


class WebsiteParser:
    """Extract title, primary page text, and visible reviews from HTML."""

    def parse(self, html: str) -> ParsedWebsite:
        """Parse one HTML document into bounded, readable text.

        Args:
            html: Raw HTML supplied by the API client.

        Returns:
            Parsed title, primary content, and up to twenty reviews.
        """
        if not html.strip():
            raise HtmlParsingError('html must contain page content')
        if len(html) > MAX_HTML_CHARS:
            raise HtmlParsingError(
                f'html must be no larger than {MAX_HTML_CHARS} characters'
            )

        soup: BeautifulSoup = BeautifulSoup(html, 'html.parser')
        for element in soup.select('script, style, noscript, svg, nav, header, footer, form'):
            element.decompose()

        title_node: Tag | None = soup.find('title')
        title: str = (
            ' '.join(title_node.get_text(' ', strip=True).split())
            if title_node else 'Untitled page'
        )
        content_node: Tag | None = soup.find('main') or soup.find('article') or soup.body
        content: str = (
            ' '.join(content_node.get_text(' ', strip=True).split())
            if content_node else ''
        )
        if not content:
            raise HtmlParsingError('html must contain page content')

        review_nodes: list[Tag] = list(soup.select(
            '[itemprop="review"], [data-review], .review, .reviews__item'
        ))[:MAX_REVIEWS]
        reviews: tuple[str, ...] = tuple(
            ' '.join(node.get_text(' ', strip=True).split())[:MAX_REVIEW_CHARS]
            for node in review_nodes
            if node.get_text(' ', strip=True)
        )

        result: ParsedWebsite = ParsedWebsite(
            title=title,
            content=content[:MAX_CONTENT_CHARS],
            reviews=reviews,
        )
        return result
