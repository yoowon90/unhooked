"""Behavior tests for extracting useful text and reviews from website HTML."""
import pytest

from website.content_parser import HtmlParsingError, ParsedWebsite, WebsiteParser


def test_parser_extracts_primary_content_and_reviews() -> None:
    """Page chrome is discarded while product copy and reviews are retained."""
    html: str = """
        <html>
          <head><title>  Everyday   Tote </title><script>secret()</script></head>
          <body>
            <nav>Account Cart</nav>
            <main>
              <h1>Everyday Tote</h1>
              <p>A lightweight canvas bag for daily errands.</p>
              <section class="review">Roomy and comfortable.</section>
              <section data-review>Strap was shorter than expected.</section>
            </main>
            <footer>Newsletter signup</footer>
          </body>
        </html>
    """

    page: ParsedWebsite = WebsiteParser().parse(html)

    assert page.title == 'Everyday Tote'
    assert 'lightweight canvas bag' in page.content
    assert 'Account Cart' not in page.content
    assert 'Newsletter signup' not in page.content
    assert page.reviews == (
        'Roomy and comfortable.',
        'Strap was shorter than expected.',
    )


def test_parser_rejects_html_without_visible_content() -> None:
    """Empty documents cannot be sent to the LLM."""
    with pytest.raises(HtmlParsingError, match='page content'):
        WebsiteParser().parse('<html><script>onlyCode()</script></html>')
