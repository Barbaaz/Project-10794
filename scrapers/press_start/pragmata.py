from bs4 import BeautifulSoup
import requests
import re
from collections import defaultdict

BASE_URL = 'https://www.pressstart.pt/pt/index.php?fc=module&module=leoproductsearch&controller=productsearch&leoproductsearch_static_token=658541fb9c2614f7870540d8c712d5a0&cate=&search_query='

nome_jogo = 'Resident Evil'
query = nome_jogo.replace(' ', '+').lower()

url = f'{BASE_URL}{query}'

print(url)

headers = {
    "User-Agent": "Mozilla/5.0"
}

resposta = requests.get(url, headers=headers)
soup = BeautifulSoup(resposta.text, "html.parser")

jogos = soup.find_all('article', class_='product-miniature js-product-miniature')

if jogos:
    print('Soup dos produtos funcionou!')
    # exit()
else:
    print('Soup dos produtos não funcionou!')

plataformas = defaultdict(list)

for jogo in jogos:
    
    # Nome
    nome = jogo.find('h3', class_='h3 product-title')
    nome = nome.get_text(strip=True) if nome else "N/A"

    # if nome:
    match = re.search(r'\b(PS5|PS4|Xbox|Nintendo Switch|Switch)\b', nome, re.IGNORECASE)

    if not match:
        continue

    consola = match.group(1) if match else None
    
    # Preço
    preco = jogo.find('span', class_='price')
    preco = preco.get_text(strip=True) if preco else "N/A"

    preco_normal = jogo.find('span', class_='regular-price')
    preco_normal = preco_normal.get_text(strip=True) if preco_normal else None

    em_promocao = preco_normal is not None
    
    # Link
    link = jogo.find('a', class_='thumbnail product-thumbnail')
    link = link['href'] if link else "N/A"
    
    # Stock
    esgotado = jogo.find('li', class_='product-flag out_of_stock')

    if esgotado:
        continue

    stock = "Disponível"

    if consola not in plataformas:
        plataformas[consola] = []
    
    plataformas[consola].append({
        "nome": nome,
        "preco": preco,
        "consola": consola,
        "stock": stock,
        "link": link
    })

for plataforma, jogos in plataformas.items():
    print(f"\n--- {plataforma} ---")
    
    for jogo in jogos:
        print(f"{jogo['nome']} | {jogo['preco']} | {jogo['stock']}")