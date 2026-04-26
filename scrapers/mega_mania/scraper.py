import requests
import time
from .parser import parse_products

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

BASE_URL = f"https://mega-mania.com.pt/pt/catalogo/"

class MegaManiaScraper:

    def fetch_page(self, url):
        response = requests.get(url, headers=HEADERS)

        if response.status_code != 200:
            raise Exception(f"Erro HTTP: {response.status_code}")

        return response.text
    
    def run(self, query):

        all_products = []
        
        query = query.replace(' ', '%20').replace("'", '')

        page = 1

        while True:
            url = f'{BASE_URL}?p={page}&f={query}&ppage=50'
            
            print(url)

            try:
                html = self.fetch_page(url)
            except Exception as e:
                print(f'Erro ao fazer scraping: {e}')
                break

            products = parse_products(html)

            if not products:
                if page == 1:
                    print("Sem produtos encontrados, parar.")
                else:
                    print("Fim das páginas")
                break

            all_products.extend(products)

            page += 1
            time.sleep(2)

        print(f"Total produtos: {len(all_products)}")

        return all_products