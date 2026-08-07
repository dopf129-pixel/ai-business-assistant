from api.ozon_client import OzonClient
from database import save_product, get_products


class ProductService:

    def __init__(self):
        self.ozon = OzonClient()

    def update_products(self):

        result = self.ozon.get_products()

        products = result["result"]["items"]

        for product in products:
            save_product(product)

        return len(products)

    def load_products(self):

        return get_products()