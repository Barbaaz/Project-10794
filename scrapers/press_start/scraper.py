import requests
import time
from .parser import parse_products
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

BASE_URL = "https://www.pressstart.pt/pt/index.php?fc=module&module=leoproductsearch&controller=productsearch&leoproductsearch_static_token=658541fb9c2614f7870540d8c712d5a0&cate=&search_query="

class PressStartScraper:

    def fetch_page(self, url):
        response = requests.get(url, headers=HEADERS)

        if response.status_code != 200:
            raise Exception(f"Erro HTTP: {response.status_code}")

        return response.text
    
    def run(self, query):

        all_products = []
        query = query.replace(' ', '+').replace("'", "%27")

        page = 1

        while True:
            if page == 1:
                url = f'{BASE_URL}{query}'
            else:
                url = f'{BASE_URL}{query}&page={page}'

            print(url)

            try:
                html = self.fetch_page(url)
            except Exception as e:
                print(f"Erro ao fazer request: {e}")
                break

            products = parse_products(html)

            if not products:
                if page == 1:
                    print("Nenhum resultado encontrado.")
                else:
                    print("Fim das páginas.")
                break
            
            all_products.extend(products)

            page += 1
            time.sleep(2)

        print(f"Total produtos: {len(all_products)}")

        return all_products