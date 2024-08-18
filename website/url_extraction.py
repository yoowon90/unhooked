import copy
import json 

class URLInfo:
    def __init__(self, soup):
        # self.brand = brand
        self.soup = soup  # BeautifulSoup(response.text, 'html.parser')
        self.data = {'name': None,
                     'price': None,
                     'description': None,
                     'currency': None,
                     'category': None,
                     'brand': None}  # initialized with all Nones
    
    def extract_brand_from_soup(self, brand):
        if brand == 'Reformation':
            self.extract_reformation()
        elif brand == 'Rouje':
            self.extract_rouje()
        elif brand == 'Zara':
            self.extract_zara()
        return self.data

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
        data_copy = copy.deepcopy(self.data)
        try:
            script_tag = self.soup.find('script', {'type': 'application/ld+json'})
            json_data = json.loads(script_tag.string)
            data_copy['name'] = json_data.get('name')
            data_copy['price'] = json_data.get('offers', {}).get('price')
            data_copy['brand'] = json_data.get('brand', {}).get('name')
            data_copy['currency'] = json_data.get('offers', {}).get('priceCurrency')
            data_copy['description'] = json_data.get('description')

        finally:
            self.__update_data(data_copy)
            return None

    def extract_rouje(self):
        # soup.find('meta'):
        # Rouje. e.g. https://www.rouje.com/products/daria-dress-jacquard-fleurs-rouge
        data_copy = copy.deepcopy(self.data)
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
            self.__update_data(data_copy)
            return None

    def extract_zara(self):
        # zara: https://www.zara.com/us/en/ribbed-dress-p00858815.html?v1=397019608&v2=2420896
        data_copy = copy.deepcopy(self.data)
        try:
            script_tag = self.soup.find('script', {'type': 'application/ld+json'})
            json_data = json.loads(script_tag.string)[0]  # json.load returns a list
            data_copy['name'] = json_data.get('name')
            data_copy['price'] = json_data.get('offers', {}).get('price')
            data_copy['brand'] = json_data.get('brand', {})
            data_copy['currency'] = json_data.get('offers', {}).get('priceCurrency')
            data_copy['description'] = json_data.get('description')

        finally:
            self.__update_data(data_copy)
            return None