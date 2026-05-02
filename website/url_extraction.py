import asyncio
import copy
import json
import inspect
import unicodedata
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse, urlunparse
import re

# Ordered keyword → dropdown-value map for category normalization.
# Order matters: more specific entries (Leggings, Dress) before broader ones (Top, Workout Gear).
_CATEGORY_KEYWORDS = [
    ('Dress',             ['dress', 'gown', 'romper', 'jumpsuit']),
    ('Skirt',             ['skirt']),
    ('Leggings',          ['legging']),
    ('Pants',             ['pant', 'trouser', 'jean', 'denim', 'shorts', 'culotte', 'chino', 'cargo']),
    ('Jacket',            ['jacket', 'coat', 'blazer', 'cardigan', 'outerwear', 'trench', 'parka', 'anorak']),
    ('Top',               ['top', 'blouse', 'shirt', 'tee', 't-shirt', 'tshirt', 'tank', 'camisole', 'cami',
                           'crop', 'tunic', 'sweater', 'sweatshirt', 'hoodie', 'pullover', 'knit']),
    ('Underwear',         ['underwear', 'lingerie', 'bra', 'bralette', 'panty', 'panties', 'thong']),
    ('Pajamas',           ['pajama', 'pyjama', 'nightwear', 'nightgown', 'sleepwear', 'loungewear']),
    ('Workout Gear',      ['workout', 'activewear', 'athletic', 'yoga', 'running', 'gym wear', 'sports bra']),
    ('Scarf',             ['scarf', 'bandana']),
    ('Bag',               ['bag', 'tote', 'handbag', 'purse', 'clutch', 'backpack', 'satchel', 'pouch', 'crossbody']),
    ('Shoes',             ['shoe', 'boot', 'sneaker', 'heel', 'sandal', 'loafer', 'mule', 'pump',
                           'stiletto', 'wedge', 'clog', 'slipper', 'espadrille', 'flat', 'footwear']),
    ('Earrings',          ['earring']),
    ('Ring',              ['ring']),
    ('Wallet',            ['wallet', 'cardholder', 'card holder', 'coin purse']),
    ('Beauty',            ['beauty', 'makeup', 'skincare', 'cosmetic', 'perfume', 'fragrance',
                           'serum', 'moisturizer', 'lipstick', 'foundation']),
    ('Living',            ['home decor', 'candle', 'bedding', 'pillow', 'throw', 'tableware']),
    ('Other accessories', ['necklace', 'bracelet', 'hat', 'belt', 'sunglasses', 'glove',
                           'headband', 'watch', 'jewelry', 'jewellery']),
]


def _normalize_category(raw: str | None, fallback_text: str | None = None) -> str | None:
    """Map a raw scraped category (or item name/description) to a fixed dropdown value.

    Checks `raw` first, then `fallback_text`, so e.g. a name like "Floral Midi Dress"
    can produce "Dress" even when the scraped category field is missing.
    """
    for text in filter(None, [raw, fallback_text]):
        lower = text.lower()
        for category, keywords in _CATEGORY_KEYWORDS:
            if any(kw in lower for kw in keywords):
                return category
    return None


# Shared headers for lightweight requests.get() fetches
_FETCH_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.8',
    'Connection': 'keep-alive',
}


def _is_blocked(html: str, status_code: int) -> bool:
    """Return True if the response looks like a CAPTCHA or bot-block page."""
    if status_code in (403, 429):
        return True
    lower = html.lower()
    if any(marker in lower for marker in [
        'captcha', 'cf-challenge', 'just a moment',
        'checking your browser', 'access denied', 'automated request',
    ]):
        return True
    # Catch silent bot-wall pages: tiny response with no meaningful title
    # (e.g. Zara/Akamai returns 200 with a 2KB shell and title='\xa0')
    if len(html) < 5000:
        from bs4 import BeautifulSoup as _BS
        soup = _BS(html, 'html.parser')
        title = (soup.title.string or '').strip() if soup.title else ''
        if not title or title in ('\xa0', '&nbsp;'):
            return True
    return False


def _try_shopify_json(url: str):
    """If the URL is a Shopify /products/ page, fetch the undocumented .json endpoint.

    Returns a standard item dict on success, or None if not applicable/failed.
    No JS rendering needed — Shopify serves full product data as plain JSON.
    """
    parsed = urlparse(url)
    if '/products/' not in parsed.path:
        return None
    path = parsed.path.rstrip('/')
    if not path.endswith('.json'):
        path = path + '.json'
    json_url = urlunparse((parsed.scheme, parsed.netloc, path, '', '', ''))
    try:
        resp = requests.get(json_url, headers=_FETCH_HEADERS, timeout=8)
        if resp.status_code != 200:
            return None
        data = resp.json()
        product = data.get('product')
        if not product:
            return None
        print(f"[shopify] Got product JSON from {json_url}")
        return _extract_from_shopify_json(product)
    except Exception as e:
        print(f"[shopify] .json fetch failed: {e}")
        return None


def _extract_from_shopify_json(product: dict) -> dict:
    """Map a Shopify product JSON object to our standard item dict."""
    body_html = product.get('body_html') or ''
    description = BeautifulSoup(body_html, 'html.parser').get_text(separator=' ').strip() if body_html else None
    variants = product.get('variants') or []
    images = product.get('images') or []
    return {
        'name': product.get('title'),
        'brand': product.get('vendor'),
        'price': variants[0].get('price') if variants else None,
        'currency': 'USD',
        'description': description or None,
        'category': product.get('product_type') or None,
        'image_url': images[0].get('src') if images else None,
    }


async def _playwright_fetch(url: str) -> str:
    """Fetch page via Playwright with stealth patches and network interception.

    Priority order:
    1. __NEXT_DATA__ (Next.js sites embed full page data here after JS runs)
    2. Intercepted JSON API responses matching product-like URL patterns
    3. Full rendered page source as fallback

    Returns either rendered HTML or a pseudo-HTML fragment wrapping the
    most useful JSON payload (parsed downstream by extract_generic).
    """
    from playwright.async_api import async_playwright
    import json as _json

    captured = {}  # resp_url -> body for product-looking JSON responses

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled'],
        )
        context = await browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/123.0.0.0 Safari/537.36'
            ),
            locale='en-US',
            viewport={'width': 1280, 'height': 800},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        product_kw = ('product', 'detail', 'pdp', 'catalog', 'item')

        async def on_response(response):
            try:
                ct = response.headers.get('content-type', '')
                if 'json' not in ct:
                    return
                resp_url = response.url
                if not any(kw in resp_url.lower() for kw in product_kw):
                    return
                body = await response.text()
                if body and len(body) > 200:
                    parsed = _json.loads(body)
                    # Only keep responses that contain actual product data (name + price)
                    if ItemDetails._find_product_in_json(parsed):
                        captured[resp_url] = body
            except Exception:
                pass

        page.on('response', on_response)

        try:
            # Use 'load' instead of 'networkidle': fires once initial HTML+scripts are
            # loaded, which is sufficient for server-rendered JSON-LD. 'networkidle'
            # never fires on sites with continuous analytics pings (e.g. Reformation).
            await page.goto(url, wait_until='load', timeout=15000)
        except Exception as e:
            print(f"[playwright] goto timed out or failed ({e}), using what loaded so far")

        # 1. Try __NEXT_DATA__
        try:
            raw = await page.evaluate("document.getElementById('__NEXT_DATA__')?.textContent || ''")
            if raw and len(raw) > 100:
                print(f"[playwright] Found __NEXT_DATA__ ({len(raw)} chars)")
                await browser.close()
                return f'<script id="__NEXT_DATA__" type="application/json">{raw}</script>'
        except Exception as e:
            print(f"[playwright] __NEXT_DATA__ extraction failed: {e}")

        # 2. Try intercepted JSON API responses (already validated to contain product data)
        for resp_url, body in list(captured.items()):
            print(f"[playwright] Captured API response from {resp_url}")
            await browser.close()
            return f'<script type="application/json" data-intercepted="true">{body}</script>'

        content = await page.content()
        await browser.close()
        return content


def fetch_page_html(url: str) -> str:
    """
    Fetch product page HTML. Tries requests.get() first (fast); falls back to
    Playwright (real Chrome) if the response looks like a CAPTCHA or block page.
    """
    try:
        response = requests.get(url, headers=_FETCH_HEADERS, timeout=5)
        if not _is_blocked(response.text, response.status_code):
            return response.text
        print(f"Bot block detected for {url}, retrying with playwright...")
    except Exception as e:
        print(f"requests.get failed ({e}), retrying with playwright...")

    return asyncio.run(_playwright_fetch(url))


def scrape_item(url: str) -> dict:
    """
    Full pipeline: fetch URL and extract item data.

    Order:
    1. Shopify .json fast path (no JS needed, bypasses Cloudflare)
    2. requests.get() + brand/generic extractor
    3. Playwright (real Chrome) if step 2 returns all-None fields
    """
    # 1. Shopify fast path
    shopify = _try_shopify_json(url)
    if shopify and any(v is not None for v in shopify.values()):
        shopify['category'] = _normalize_category(
            shopify.get('category'),
            fallback_text=f"{shopify.get('name', '')} {shopify.get('description', '')}",
        )
        return shopify

    html = fetch_page_html(url)
    result = ItemDetails(BeautifulSoup(html, 'html.parser')).get_item_data()

    # All None means the page likely needs JS to render — retry with Playwright
    data_fields = {k: v for k, v in result.items() if k != 'image_url'}
    if all(v is None for v in data_fields.values()):
        print(f"All fields None after initial fetch, retrying {url} with playwright...")
        try:
            html = asyncio.run(_playwright_fetch(url))
            result = ItemDetails(BeautifulSoup(html, 'html.parser')).get_item_data()
        except Exception as e:
            print(f"Playwright retry failed: {e}")

    result['category'] = _normalize_category(
        result.get('category'),
        fallback_text=f"{result.get('name', '')} {result.get('description', '')}",
    )
    return result

BRANDS = ['Reformation',
          'Rouje',
          'Zara',
          'American Vintage',
          'Aritzia',
          'A.P.C',
          'Bloomingdales',
          'DÔEN',
          'MANGO',
        ]

# Reformation method worked with Vuori & ssense


# TODO: Tiffany & Co. For Love and Lemons.
# TODO: Denied: Free People, Massimo Dutti, Ralph Lauren, Aritzia, Sezane,  & Other Stories


class ItemDetails:
    def __init__(self, soup):
        # initialize default data with all Nones
        self.__default_data = {'name': None,
                               'price': None,
                               'description': None,
                               'currency': None,
                               'category': None,
                               'brand': None,
                               'image_url': None}
        self.soup = soup  # BeautifulSoup(response.text, 'html.parser')
        self.brands = BRANDS

    def get_extract_methods(self):
        """Get all methods that start with 'extract_'."""
        methods = inspect.getmembers(self, predicate=inspect.ismethod)
        extract_methods = {name: method for name, method in methods if name.startswith('extract_')}
        return extract_methods

    def extract_reformation(self):
        data_copy = copy.deepcopy(self.__default_data)
        try:
            script_tag = self.soup.find('script', {'type': 'application/ld+json'})
            json_data = json.loads(script_tag.string)
            data_copy['name'] = json_data.get('name')
            data_copy['price'] = json_data.get('offers', {}).get('price')
            data_copy['brand'] = json_data.get('brand', {}).get('name')
            data_copy['currency'] = json_data.get('offers', {}).get('priceCurrency')
            data_copy['description'] = json_data.get('description')
        except Exception as e:
            print(f"extract_reformation failed: {e}")
        return data_copy

    def extract_aritzia(self):
        # TODO: Aritzia has blocked scraping. Pydoll fallback may help.
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup
            data_copy['name'] = soup.find('meta', {'property': 'og:title'}).get('content')
            data_copy['price'] = soup.find('meta', {'property': 'og:price:amount'}).get('content')
            data_copy['currency'] = soup.find('meta', {'property': 'og:price:currency'}).get('content')
            data_copy['description'] = (f"{soup.find('meta', {'property': 'og:description'}).get('content')}."
                                        f" {soup.find('meta', {'property': 'product:color'}).get('content')}"
                                        f" ({soup.find('meta', {'property': 'product:color:map'}).get('content')})")
        except Exception as e:
            print(f"extract_aritzia failed: {e}")
        return data_copy

    def extract_rouje(self):
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup
            script_tag = soup.find('script', {'type': 'application/json', 'data-layer-product-details': True})
            json_data = json.loads(script_tag.string)
            data_copy['name'] = json_data.get("item_name")
            data_copy['price'] = json_data.get("price")
            data_copy['currency'] = json_data.get("currency")
            data_copy['brand'] = json_data.get("item_brand")
            data_copy['category'] = json_data.get("item_category")
            data_copy['description'] = soup.find('meta', {'property': 'og:description'}).get('content')
        except Exception as e:
            print(f"extract_rouje failed: {e}")
        return data_copy

    def extract_zara(self):
        # Zara is a JS SPA — this works after pydoll renders the page.
        data_copy = copy.deepcopy(self.__default_data)
        try:
            script_tag = self.soup.find('script', {'type': 'application/ld+json'})
            json_data = json.loads(script_tag.string)
            # Zara wraps schema in a list; handle both forms
            if isinstance(json_data, list):
                json_data = json_data[0]
            data_copy['name'] = json_data.get('name')
            data_copy['price'] = json_data.get('offers', {}).get('price')
            data_copy['brand'] = json_data.get('brand', {}).get('name') if isinstance(json_data.get('brand'), dict) else json_data.get('brand')
            data_copy['currency'] = json_data.get('offers', {}).get('priceCurrency')
            data_copy['description'] = json_data.get('description')
        except Exception as e:
            print(f"extract_zara failed: {e}")
        return data_copy

    def extract_apc(self):
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup
            data_copy['name'] = soup.find('meta', {'property': 'og:title'}).get('content')
            data_copy['brand'] = soup.find('meta', {'property': 'og:site_name'}).get('content')
            data_copy['price'] = soup.find('meta', {'property': 'product:price:amount'}).get('content')
            data_copy['currency'] = soup.find('meta', {'property': 'product:price:currency'}).get('content')
            data_copy['description'] = soup.find('meta', {'property': 'og:description'}).get('content')
        except Exception as e:
            print(f"extract_apc failed: {e}")
        return data_copy

    def extract_bloomingdales(self):
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup
            script_tag = soup.find('script', {'id': 'productMktData'})
            json_data = json.loads(script_tag.string)
            data_copy['brand'] = json_data.get('brand').get('name')
            data_copy['name'] = json_data.get('name')
            data_copy['price'] = json_data.get('offers')[0].get('price')
            data_copy['currency'] = json_data.get('offers')[0].get('priceCurrency')
            data_copy['description'] = soup.find('meta', {'property': 'og:title'}).get('content')
        except Exception as e:
            print(f"extract_bloomingdales failed: {e}")
        return data_copy

    def extract_doen(self):
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup
            data_copy['brand'] = soup.find('meta', {'property': 'og:site_name'}).get('content')
            data_copy['name'] = soup.find('meta', {'property': 'og:title'}).get('content')
            data_copy['price'] = soup.find('meta', {'property': 'og:price:amount'}).get('content')
            data_copy['currency'] = soup.find('meta', {'property': 'og:price:currency'}).get('content')
            data_copy['description'] = soup.find('meta', {'property': 'og:description'}).get('content')
        except Exception as e:
            print(f"extract_doen failed: {e}")
        return data_copy

    def extract_mango(self):
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup
            data_copy['brand'] = soup.find('meta', {'property': 'og:site_name'}).get('content')
            data_copy['name'] = soup.find('meta', {'property': 'og:title'}).get('content')
            data_copy['price'] = soup.find('meta', {'itemprop': 'price'}).get('content')
            data_copy['currency'] = soup.find('meta', {'itemprop': 'priceCurrency'}).get('content')
            data_copy['description'] = soup.find('meta', {'property': 'og:description'}).get('content')
        except Exception as e:
            print(f"extract_mango failed: {e}")
        return data_copy

    def extract_image_url(self):
        """Extract the main product image URL from the page"""
        try:
            soup = self.soup

            # Try multiple common image selectors
            image_selectors = [
                'meta[property="og:image"]',
                'meta[name="twitter:image"]',
                'meta[property="product:image"]',
                'meta[itemprop="image"]',
                'link[rel="image_src"]'
            ]

            for selector in image_selectors:
                img_meta = soup.select_one(selector)
                if img_meta:
                    image_url = img_meta.get('content') or img_meta.get('href')
                    if image_url:
                        return image_url

            # Fallback: look for the first large image in the page
            images = soup.find_all('img')
            for img in images:
                src = img.get('src')
                if src and any(keyword in src.lower() for keyword in ['product', 'main', 'hero', 'featured']):
                    return src

            return None

        except Exception as e:
            print(f"Error extracting image: {e}")
            return None

    @staticmethod
    def google_search_image_fallback(brand, name, description, price):
        """Fallback method to search Google for product images when direct extraction fails"""
        try:
            # Construct search query from brand, name, and description
            search_terms = []
            if brand:
                search_terms.append(brand)
            if name:
                search_terms.append(name)
            if description:
                # Clean description to get key terms
                desc_clean = re.sub(r'[^\w\s]', '', description)
                search_terms.append(desc_clean)
            if price:
                search_terms.append(price)
            if not search_terms:
                return None

            # Create search query - add "product" to make it more specific
            search_query = ' '.join(search_terms)
            print(f"Google search fallback for: {search_query}")

            # Try multiple search strategies
            search_strategies = [
                # f"https://www.google.com/search?q={quote_plus(search_query)}",
                # f"https://www.google.com/search?q={quote_plus(search_query)}&tbm=shop",  # Shopping tab
                f"https://www.google.com/search?q={quote_plus(search_query)}&tbm=isch"   # Image search
            ]

            # Headers to mimic a real browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }

            for search_url in search_strategies:
                try:
                    print(f"Trying search strategy: {search_url}")
                    response = requests.get(search_url, headers=headers, timeout=15)
                    response.raise_for_status()

                    # Parse the response to find image URLs
                    # Look for common image patterns in Google search results
                    image_patterns = [
                        r'https://[^"\s]+\.(?:jpg|jpeg|png|webp|gif)',
                        r'https://[^"\s]+/images/[^"\s]+',
                        r'https://[^"\s]+/products/[^"\s]+',
                        r'https://[^"\s]+/assets/[^"\s]+',
                        r'https://[^"\s]+/media/[^"\s]+',
                    ]

                    for pattern in image_patterns:
                        matches = re.findall(pattern, response.text)
                        if matches:
                            # Filter out common non-product images and prioritize product images
                            filtered_matches = []
                            for url in matches:
                                url_lower = url.lower()
                                # Skip Google's own images
                                if any(exclude in url_lower for exclude in [
                                    'google.com', 'gstatic.com', 'googleusercontent.com',
                                    'logo', 'icon', 'avatar', 'banner', 'advertisement'
                                ]):
                                    continue

                                # Prioritize images that look like product images
                                if any(priority in url_lower for priority in [
                                    'product', 'item', 'goods', 'merchandise'
                                ]):
                                    filtered_matches.insert(0, url)  # Add to front
                                else:
                                    filtered_matches.append(url)

                            if filtered_matches:
                                print(f"Found fallback image: {filtered_matches[0]}")
                                return filtered_matches[0]

                    # Add delay between requests to be respectful
                    # import time
                    # time.sleep(1)

                except Exception as e:
                    print(f"Error with search strategy {search_url}: {e}")
                    continue

            return None

        except Exception as e:
            print(f"Error in Google search fallback: {e}")
            return None

    @staticmethod
    def _method_name(brand: str) -> str:
        """Normalize brand name to extract_<suffix> method name.
        Strips accents, dots, and lowercases so e.g. 'A.P.C' → 'extract_apc', 'DÔEN' → 'extract_doen'."""
        normalized = unicodedata.normalize('NFKD', brand).encode('ascii', 'ignore').decode('ascii')
        suffix = normalized.lower().replace(' ', '_').replace('.', '').replace('-', '_')
        return f'extract_{suffix}'

    @staticmethod
    def _find_product_in_json(obj, depth=0):
        """Walk an arbitrary JSON structure and return the first dict that looks like a product."""
        if depth > 6:
            return None
        if isinstance(obj, dict):
            # A product-like dict has at least a name and a price
            if obj.get('name') and ('price' in obj or 'offers' in obj):
                return obj
            for v in obj.values():
                found = ItemDetails._find_product_in_json(v, depth + 1)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj[:5]:
                found = ItemDetails._find_product_in_json(item, depth + 1)
                if found:
                    return found
        return None

    @staticmethod
    def _fill_from_product_dict(data_copy, product):
        """Populate data_copy from a schema.org-ish product dict."""
        data_copy['name'] = product.get('name')
        data_copy['description'] = product.get('description')
        brand = product.get('brand')
        data_copy['brand'] = brand.get('name') if isinstance(brand, dict) else brand
        offers = product.get('offers') or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price_val = product.get('price') or offers.get('price') or offers.get('value') or offers.get('amount')
        data_copy['price'] = str(price_val) if price_val is not None else None
        data_copy['currency'] = (offers.get('priceCurrency') or offers.get('currency')
                                 or product.get('priceCurrency') or product.get('currency'))

    def extract_generic(self):
        """
        Last-resort extractor for any site. Tries (in order):
        1. __NEXT_DATA__ embedded JSON (Next.js SSR sites)
        2. CDP-intercepted API JSON (data-intercepted script tag from _pydoll_fetch)
        3. schema.org Product JSON-LD blocks
        4. OpenGraph / itemprop meta tags
        """
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup

            # 1. __NEXT_DATA__ (Next.js sites — pydoll pseudo-HTML or real page)
            next_script = soup.find('script', {'id': '__NEXT_DATA__'})
            if next_script and next_script.string:
                try:
                    next_data = json.loads(next_script.string)
                    page_props = next_data.get('props', {}).get('pageProps', {})
                    product = self._find_product_in_json(page_props)
                    if product:
                        self._fill_from_product_dict(data_copy, product)
                        if any(v is not None for v in data_copy.values()):
                            print("extract_generic: matched via __NEXT_DATA__")
                            return data_copy
                except Exception as e:
                    print(f"extract_generic __NEXT_DATA__ parse failed: {e}")

            # 2. CDP-intercepted API JSON
            api_script = soup.find('script', {'data-intercepted': 'true'})
            if api_script and api_script.string:
                try:
                    api_data = json.loads(api_script.string)
                    product = self._find_product_in_json(api_data)
                    if product:
                        self._fill_from_product_dict(data_copy, product)
                        if any(v is not None for v in data_copy.values()):
                            print("extract_generic: matched via intercepted API response")
                            return data_copy
                except Exception as e:
                    print(f"extract_generic intercepted API parse failed: {e}")

            # 3. JSON-LD Product schema
            for script in soup.find_all('script', {'type': 'application/ld+json'}):
                try:
                    json_data = json.loads(script.string)
                    if isinstance(json_data, list):
                        json_data = next((d for d in json_data if d.get('@type') == 'Product'), json_data[0])
                    if json_data.get('@type') == 'Product':
                        self._fill_from_product_dict(data_copy, json_data)
                        if any(v is not None for v in data_copy.values()):
                            print("extract_generic: matched via JSON-LD Product schema")
                            return data_copy
                except Exception:
                    continue

            # 4. OpenGraph / itemprop meta tags
            def og(prop):
                tag = soup.find('meta', {'property': prop}) or soup.find('meta', {'name': prop})
                return tag.get('content') if tag else None

            def itemprop(prop):
                tag = soup.find('meta', {'itemprop': prop})
                return tag.get('content') if tag else None

            data_copy['name'] = og('og:title')
            data_copy['brand'] = og('og:site_name')
            data_copy['price'] = (og('og:price:amount') or og('product:price:amount') or itemprop('price'))
            data_copy['currency'] = (og('og:price:currency') or og('product:price:currency') or itemprop('priceCurrency'))
            data_copy['description'] = og('og:description')

            if any(v is not None for v in data_copy.values()):
                print("extract_generic: matched via OpenGraph tags")

        except Exception as e:
            print(f"extract_generic failed: {e}")
        return data_copy

    def get_item_data(self):
        extract_methods = self.get_extract_methods()
        matches = {brand: dict() for brand in self.brands}

        for brand in self.brands:
            method_name = self._method_name(brand)
            if method_name in extract_methods:
                result = extract_methods[method_name]()
                print(f"{brand} → {method_name}: {result}")
                matches[brand] = dict(
                    name=result['name'],
                    price=result['price'],
                    description=result['description'],
                    currency=result['currency'],
                    brand=result['brand'],
                    category=result['category'],
                )
            else:
                print(f"{brand} → {method_name}: no extractor")

        match_counts = {brand: sum(1 for v in d.values() if v is not None) for brand, d in matches.items()}
        max_matches = max(match_counts.values())
        if max_matches == 0:
            print("No brand-specific matches. Trying generic extractor...")
            result = self.extract_generic()
        else:
            brand_detections = [b for b, count in match_counts.items() if count == max_matches and b is not None]
            if brand_detections:
                print(f"Matched brand: {brand_detections[0]}")
                result = matches[brand_detections[0]]
            else:
                best_brand = [b for b, count in match_counts.items() if count == max_matches][0]
                result = matches[best_brand]

        # Add image URL to the result
        result['image_url'] = self.extract_image_url()
        print(f"Image URL: {result['image_url']}")

        return result
