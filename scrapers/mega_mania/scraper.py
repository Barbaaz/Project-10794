import requests
import time
from .parser import parse_products

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

BASE_URL = "https://mega-mania.com.pt/pt/catalogo/?f="


class MegaManiaScraper:

    def fetch_page(self, url):
        response = requests.get(url, headers=HEADERS)

        if response.status_code != 200:
            raise Exception(f"Erro HTTP: {response.status_code}")

        return response.text

    def run(self, query):

        all_products = []

        # query = 'resident evil'
        query = query.replace(' ', '%20')
        query = query +'&ppage=50'

        url = f'{BASE_URL}{query}'

        print(url)

        try:
            html = self.fetch_page(url)
            products = parse_products(html)

            if not products:
                print("Sem produtos encontrados, parar.")

            all_products.extend(products)

            time.sleep(2)

        except Exception as e:
            print(f"Erro: {e}")

        print(f"Total produtos: {len(all_products)}")

        return all_products