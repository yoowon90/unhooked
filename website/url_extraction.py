import asyncio
import copy
import json
import inspect
import unicodedata
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import re

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
    return any(marker in lower for marker in [
        'captcha', 'cf-challenge', 'just a moment',
        'checking your browser', 'access denied', 'automated request',
    ])


async def _pydoll_fetch(url: str) -> str:
    """Fetch page HTML via a real Chrome instance (avoids bot detection + Cloudflare)."""
    from pydoll.browser import Chrome
    async with Chrome() as browser:
        browser.options.headless = True  # remove this line if a site detects headless via canvas/WebGL fingerprinting despite pydoll's bot mitigations
        tab = await browser.start()
        await tab.enable_auto_solve_cloudflare_captcha()
        await tab.go_to(url, timeout=30)
        return await tab.page_source


def fetch_page_html(url: str) -> str:
    """
    Fetch product page HTML. Tries requests.get() first (fast); falls back to
    pydoll (real Chrome, ~2-3s) if the response looks like a CAPTCHA or block page.
    """
    try:
        response = requests.get(url, headers=_FETCH_HEADERS, timeout=5)
        if not _is_blocked(response.text, response.status_code):
            return response.text
        print(f"Bot block detected for {url}, retrying with pydoll...")
    except Exception as e:
        print(f"requests.get failed ({e}), retrying with pydoll...")

    return asyncio.run(_pydoll_fetch(url))


def scrape_item(url: str) -> dict:
    """
    Full pipeline: fetch URL and extract item data.
    If requests succeeds but all fields are None (e.g. JS-rendered page),
    automatically retries with pydoll before giving up.
    """
    html = fetch_page_html(url)
    result = ItemDetails(BeautifulSoup(html, 'html.parser')).get_item_data()

    # All None means the page likely needs JS to render product data — retry with pydoll
    data_fields = {k: v for k, v in result.items() if k != 'image_url'}
    if all(v is None for v in data_fields.values()):
        print(f"All fields None after initial fetch, retrying {url} with pydoll...")
        try:
            html = asyncio.run(_pydoll_fetch(url))
            result = ItemDetails(BeautifulSoup(html, 'html.parser')).get_item_data()
        except Exception as e:
            print(f"Pydoll retry failed: {e}")

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

    def get_item_data(self):
        extract_methods = self.get_extract_methods()
        matches = {brand: dict() for brand in self.brands}

        for brand in self.brands:
            method_name = self._method_name(brand)
            if method_name in extract_methods:
                result = extract_methods[method_name]()
                print(f"{brand} → {method_name}: {result}")
                # Use a separate variable to avoid shadowing the loop variable
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

        # get the brand with the most matches. if multiple, pick one where brand_extract_dict['brand'] is equal to brand.
        # if still multiple, pick the first one
        match_counts = {brand: sum([1 for value in brand_dict.values() if value is not None]) for brand, brand_dict in matches.items()}
        max_matches = max(match_counts.values())
        if max_matches == 0:
            print("No matches found. Using default data..")
            result = self.__default_data
        else:
            # first filter bratches that have a brand among the matches
            brand_detections = [brand for brand, count in match_counts.items() if count == max_matches and brand is not None]
            if len(brand_detections):
                print(f"There has been a match and a branch detection: {brand_detections[0]}")
                result = matches[brand_detections[0]]
            else:
                print("There has been a match, but no branch match. Using url extraction with the most matches..")
                # get the brand with the most matches
                best_brand = [brand for brand, count in match_counts.items() if count == max_matches][0]
                result = matches[best_brand]

        # Add image URL to the result
        result['image_url'] = self.extract_image_url()
        print(f"Image URL: {result['image_url']}")

        return result
