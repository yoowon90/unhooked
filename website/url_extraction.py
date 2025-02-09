import copy
import json
import inspect

BRANDS = ['Reformation',
          'Rouje', 
          'Zara', 
          'Aamerican Vintage', 
          'Aritzia', 
          'A.P.C',
          'Bloomingdales',
          'DÔEN',
          'MANGO',
        ]  

# Reformation method worked with Vuori & ssense


# TODO: Tiffany & Co., For Love and Lemons

# TODO: Denied: Free People, Massimo Dutti, Ralph Lauren, Aritzia, Sezane,  & Other Stories


class ItemDetails:
    def __init__(self, soup):
        # initialize default data with all Nones
        self.__default_data = {'name': None,
                               'price': None,
                               'description': None,
                               'currency': None,
                               'category': None,
                               'brand': None}
        self.soup = soup  # BeautifulSoup(response.text, 'html.parser')
        self.brands = BRANDS
    
    def get_extract_methods(self):
        """Get all methods that start with 'extract_'."""
        methods = inspect.getmembers(self, predicate=inspect.ismethod)
        extract_methods = {name: method for name, method in methods if name.startswith('extract_')}
        return extract_methods

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
            return self.__default_data
        else:
            # first filter bratches that have a brand among the matches
            brand_detections = [brand for brand, count in match_counts.items() if count == max_matches and brand is not None]
            if len(brand_detections):
                print(f"There has been a match and a branch detection: {brand_detections[0]}")
                return matches[brand_detections[0]]
            else:
                print("There has been a match, but no branch match. Using url extraction with the most matches..")
                # get the brand with the most matches
                best_brand = [brand for brand, count in match_counts.items() if count == max_matches][0]
                return matches[best_brand]
    
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