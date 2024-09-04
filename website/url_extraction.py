import copy
import json 

BRANDS = ['Reformation', 'Rouje', 'Zara', 'Aamerican Vintage', 'Aritzia']  # TODO: Massimo Dutti, Mango, Sezane, Free People, & Other Stories, Aritzia

class URLInfo:
    def __init__(self, soup):
        self.soup = soup  # BeautifulSoup(response.text, 'html.parser')
        self.__default_data = {'name': None,
                     'price': None,
                     'description': None,
                     'currency': None,
                     'category': None,
                     'brand': None}  # initialized with all Nones

    def extract_item_data(self):
        for brand in BRANDS: 
            print(f"extraction started with {brand}")
            brand_extract_dict = self.extract_brand_from_soup(brand)
            print(f"brand extract dict: {brand_extract_dict}")
            name, price, description, currency, brand, category = (brand_extract_dict['name'],
                                                         brand_extract_dict['price'],
                                                         brand_extract_dict['description'],
                                                         brand_extract_dict['currency'],
                                                         brand_extract_dict['brand'],
                                                         brand_extract_dict['category'])
            if not (name is None and price is None and description is None
                and currency is None and brand is None):
                print("Some valid data found")
                return brand_extract_dict
                # break
            else:
                print("No data found")

    def extract_brand_from_soup(self, brand):
        if brand == 'Reformation' or brand == 'American Vintage':
            return self.extract_reformation()
        elif brand == 'Rouje':
            return self.extract_rouje()
        elif brand == 'Zara':
            return self.extract_zara()
        elif brand == 'Massimo Dutti':
            return self.extract_massimo_dutti()
        elif brand == 'Aritzia':
            return self.extract_aritzia()
        else:
            return self.__default_data

    def __update_data(self, new_data):
        """ Update data with valid new data. 
            Keep data's value as none if key was not extracted to new_data
        """
        for key in new_data.keys():
            if new_data[key] is not None:
                self.data[key] = new_data[key]
    
    def extract_reformation(self):
        """ Extracts data from Reformation website """
        # Reformation. e.g. https://www.thereformation.com/products/tam-knit-dress/1306570SLA0XS.html
        data_copy = copy.deepcopy(self.__default_data)
        try:
            script_tag = self.soup.find('script', {'type': 'application/ld+json'})
            json_data = json.loads(script_tag.string)
            data_copy['name'] = json_data.get('name')
            data_copy['price'] = json_data.get('offers', {}).get('price')
            data_copy['brand'] = json_data.get('brand', {}).get('name')
            data_copy['currency'] = json_data.get('offers', {}).get('priceCurrency')
            data_copy['description'] = json_data.get('description')

        finally:
            return data_copy
    
    def extract_massimo_dutti(self):
        # Massimo Dutti. e.g. https://www.massimodutti.com
        data_copy = copy.deepcopy(self.__default_data)
        try:
            soup = self.soup
            # use selenium
            # https://stackoverflow.com/questions/52687372/beautifulsoup-not-returning-complete-html-of-the-page
        
        finally:
            return data_copy
    
    def extract_aritzia(self):
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
        # soup.find('meta'):
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
        # zara: https://www.zara.com/us/en/ribbed-dress-p00858815.html?v1=397019608&v2=2420896
        data_copy = copy.deepcopy(self.__default_data)
        try:
            script_tag = self.soup.find('script', {'type': 'application/ld+json'})
            json_data = json.loads(script_tag.string)[0]  # json.load returns a list
            data_copy['name'] = json_data.get('name')
            data_copy['price'] = json_data.get('offers', {}).get('price')
            data_copy['brand'] = json_data.get('brand', {})
            data_copy['currency'] = json_data.get('offers', {}).get('priceCurrency')
            data_copy['description'] = json_data.get('description')

        finally:
            return data_copy