import copy
import json
import inspect
import requests
from urllib.parse import quote_plus
import re

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
        """ Extracts data from Reformation website """
        # Reformation. e.g. https://www.thereformation.com/products/tam-knit-dress/1306570SLA0XS.html
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup
            script_tag = soup.find('script', {'type': 'application/ld+json'})
            json_data = json.loads(script_tag.string)
            data_copy['name'] = json_data.get('name')
            data_copy['price'] = json_data.get('offers', {}).get('price')
            data_copy['brand'] = json_data.get('brand', {}).get('name')
            data_copy['currency'] = json_data.get('offers', {}).get('priceCurrency')
            data_copy['description'] = json_data.get('description')

        finally:
            return data_copy

    def extract_aritzia(self):
        """ Extracts data from Artizia website """
        #  TODO: Aritzia has blocked the scraping. Need to find a way to bypass it.
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup
            data_copy['name'] = soup.find('meta', {'property': 'og:title'}).get('content')
            data_copy['price'] = soup.find('meta', {'property': 'og:price:amount'}).get('content')
            data_copy['currency'] = soup.find('meta', {'property': 'og:price:currency'}).get('content')
            data_copy['description'] = (f"{soup.find('meta', {'property': 'og:description'}).get('content')}."
                                        f" {soup.find('meta', {'property': 'product:color'}).get('content')}"
                                        f" ({soup.find('meta', {'property': 'product:color:map'}).get('content')})")
        finally:
            return data_copy

    def extract_rouje(self):
        """ Extracts data from Rouje website """
        # Rouje. e.g. https://www.rouje.com/products/daria-dress-jacquard-fleurs-rouge
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup
            script_tag = soup.find('script', {'type': 'application/json', 'data-layer-product-details': True})
            # if script_tag:
            json_data = json.loads(script_tag.string)
            data_copy['name'] = json_data.get("item_name")
            data_copy['price'] = json_data.get("price")
            data_copy['currency'] = json_data.get("currency")
            data_copy['brand'] = json_data.get("item_brand")
            data_copy['category'] = json_data.get("item_category")

            # get description from meta tag
            data_copy['description'] = soup.find('meta', {'property': 'og:description'}).get('content')

        finally:
            return data_copy

    def extract_zara(self):
        """ Extracts data from Zara website """
        # zara: https://www.zara.com/us/en/ribbed-dress-p00858815.html?v1=397019608&v2=2420896
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup
            script_tag = soup.find('script', {'type': 'application/ld+json'})
            json_data = json.loads(script_tag.string)[0]  # json.load returns a list
            data_copy['name'] = json_data.get('name')
            data_copy['price'] = json_data.get('offers', {}).get('price')
            data_copy['brand'] = json_data.get('brand', {})
            data_copy['currency'] = json_data.get('offers', {}).get('priceCurrency')
            data_copy['description'] = json_data.get('description')

        finally:
            return data_copy

    def extract_apc(self):
        """ Extracts data from APC website """
        # apc: https://www.apc-us.com/products/blouse-julienne-vialq-f13433_aac?variant=42911449219171&currency=USD&utm_source=social&utm_medium=cpc&utm_campaign=Vervaunt_Social+%2F+CPC_APC_US_Conversion_DPA&utm_term=Remarketing_All+Remarketing+-+%28Mixed+Genders%29&utm_content=Remarketing+DPA&fbadid=120209825233840351&fbclid=PAZXh0bgNhZW0BMABhZGlkAasUnIl9ZV8BpmzeIVNQRlHAMvvI9IZnoPv4szx-vIU1wOcCbGn01e40ocq1ncWS72OwPw_aem_rQ_UuHCVYzaA5g6u_VSKTA&campaign_id=120209825200840351&ad_id=120209825233840351
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup
            data_copy['name'] = soup.find('meta', {'property': 'og:title'}).get('content')
            data_copy['brand'] = soup.find('meta', {'property': 'og:site_name'}).get('content')
            data_copy['price'] = soup.find('meta', {'property': 'product:price:amount'}).get('content')
            data_copy['currency'] = soup.find('meta', {'property': 'product:price:currency'}).get('content')
            data_copy['description'] = soup.find('meta', {'property': 'og:description'}).get('content')

        finally:
            return data_copy

    def extract_bloomingdales(self):
        """ Extracts data from Bloomingdales website """
        # bloomingdales: https://www.bloomingdales.com/shop/product/cinq-a-sept-naia-faux-shearling-jacket?ID=5274338&upc_ID=7969176&Quantity=1&seqNo=3&EXTRA_PARAMETER=BAG&pickInStore=false
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

        finally:
            return data_copy


    def extract_doen(self):
        """ Extracts data from DÔEN website """
        # doen: https://www.bloomingdales.com/shop/product/cinq-a-sept-naia-faux-shearling-jacket?ID=5274338&upc_ID=7969176&Quantity=1&seqNo=3&EXTRA_PARAMETER=BAG&pickInStore=false
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup
            data_copy['brand'] = soup.find('meta', {'property': 'og:site_name'}).get('content')
            data_copy['name'] = soup.find('meta', {'property': 'og:title'}).get('content')
            data_copy['price'] = soup.find('meta', {'property': 'og:price:amount'}).get('content')
            data_copy['currency'] = soup.find('meta', {'property': 'og:price:currency'}).get('content')
            data_copy['description'] = soup.find('meta', {'property': 'og:description'}).get('content')

        finally:
            return data_copy

    def extract_mango(self):
        """ Extracts data from Mango website """
        # mango: https://shop.mango.com/us/en/p/women/tops/party/lurex-top-with-openwork-details_87054063?c=OR
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup
            data_copy['brand'] = soup.find('meta', {'property': 'og:site_name'}).get('content')
            data_copy['name'] = soup.find('meta', {'property': 'og:title'}).get('content')
            data_copy['price'] = soup.find('meta', {'itemprop': 'price'}).get('content')
            data_copy['currency'] = soup.find('meta', {'itemprop': 'priceCurrency'}).get('content')
            data_copy['description'] = soup.find('meta', {'property': 'og:description'}).get('content')

        finally:
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

    def google_search_image_fallback(self, brand, name, description):
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
                desc_clean = re.sub(r'[^\w\s]', ' ', description)
                desc_words = desc_clean.split()[:5]  # Take first 5 words
                search_terms.extend(desc_words)

            if not search_terms:
                return None

            # Create search query - add "product" to make it more specific
            search_query = ' '.join(search_terms) + ' product'
            print(f"Google search fallback for: {search_query}")

            # Try multiple search strategies
            search_strategies = [
                f"https://www.google.com/search?q={quote_plus(search_query)}",
                f"https://www.google.com/search?q={quote_plus(search_query)}&tbm=shop",  # Shopping tab
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
                    import time
                    time.sleep(1)

                except Exception as e:
                    print(f"Error with search strategy {search_url}: {e}")
                    continue

            return None

        except Exception as e:
            print(f"Error in Google search fallback: {e}")
            return None

    def get_item_data(self):
        """
        Get item data by trying extraction methods of all brand in BRANDS.
        Chooses the brand with the most matches of all fields, by first choosing
        the extraction that detected a not None brand.
        """
        # get all extract methods
        extract_methods = self.get_extract_methods()

        # intialize dict to count # of matches for each brand
        matches = {brand: dict() for brand in self.brands}

        for brand in self.brands:
            print(f"Extraction started with {brand}...")
            method_name = f'extract_{brand.lower().replace(" ", "_")}'
            print(f"Method name for {brand} is {method_name}")
            if method_name in extract_methods:
                brand_extract_dict = extract_methods[method_name]()
                print(f"brand extract dict: {brand_extract_dict}")
                name, price, description, currency, brand, category = (brand_extract_dict['name'],
                                                         brand_extract_dict['price'],
                                                         brand_extract_dict['description'],
                                                         brand_extract_dict['currency'],
                                                         brand_extract_dict['brand'],
                                                         brand_extract_dict['category'])
                matches[brand] = dict(name=name, price=price, description=description, currency=currency, brand=brand, category=category)

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

        # If direct image extraction failed, try Google search fallback
        if not result['image_url']:
            print("Direct image extraction failed, trying Google search fallback...")
            fallback_image = self.google_search_image_fallback(
                result.get('brand'),
                result.get('name'),
                result.get('description')
            )
            if fallback_image:
                result['image_url'] = fallback_image
                print(f"Successfully found fallback image: {fallback_image}")
            else:
                print("Google search fallback also failed")

        return result
