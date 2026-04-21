# from bs4 import BeautifulSoup
# import requests

# BASE_URL = 'https://www.pressstart.pt/pt/jogos'

# consola = 'ps5'
# nome_jogo = 'Slave Zero X Calamity Edition PS5'
# nome_jogo = nome_jogo.replace(' ', '-').lower()

# url = f'{BASE_URL}-{consola}/{nome_jogo}.html' # https://www.pressstart.pt/pt/jogos-ps5/slave-zero-x-calamity-edition-ps5.html'

# print(url)

# resposta = requests.get(url)

# soup = BeautifulSoup(resposta.text, "html.parser")
# desconto = soup.find('div', class_='product-price h5 has-discount')
# esgotado = soup.find('li', class_='product-flag out_of_stock')

# if desconto:
#     print('Produto com desconto!')

# if esgotado:
#     print('Produto sem stock!')
# else:
#     print('Preço atual: ', soup.find('span', class_='current-price-value') .get_text(strip=True))
#     print('Preço normal: ', soup.find('span', class_='regular-price') .get_text(strip=True))

# from bs4 import BeautifulSoup
# import requests

# from utils import limpar_preco, extrair_consola, limpar_nome
# from models import criar_produto

# def scraper_pressstart(query):

#     BASE_URL = 'https://www.pressstart.pt/pt/index.php?fc=module&module=leoproductsearch&controller=productsearch&leoproductsearch_static_token=658541fb9c2614f7870540d8c712d5a0&cate=&search_query='

#     url = f'{BASE_URL}{query}'

#     headers = {'User-Agent': 'Mozilla/5.0'}
#     resposta = requests.get(url, headers=headers)

#     soup = BeautifulSoup(resposta.text, "html.parser")

#     jogos_html = soup.find_all('article', class_='product-miniature js-product-miniature')

#     jogos = []

#     for j in jogos_html:

#         nome = j.select_one('.product-title a')
#         nome = nome.get_text(strip=True) if nome else None

#         if not nome:
#             continue

#         consola = extrair_consola(nome)
#         if not consola:
#             continue

#         if j.select_one('.out_of_stock'):
#             continue

#         preco = limpar_preco(j.select_one('.price').get_text(strip=True)) if j.select_one('.price') else None

#         preco_antigo = limpar_preco(j.select_one('.regular-price').get_text(strip=True)) if j.select_one('.regular-price') else None

#         link = j.find('a', class_='thumbnail product-thumbnail')
#         link = link['href'] if link else "N/A"

#         jogo = criar_produto(nome, consola, preco, preco_antigo, True, 'Press Start', link)

#         jogos.append(jogo)

#     return jogos

# resultados = scraper_pressstart('persona+5')

# for r in resultados:
#     print(r)

from scrapers.press_start.scraper import PressStartScraper

scraper = PressStartScraper()
products = scraper.run(max_pages=2)

for p in products[:5]:
    print(p)