from bs4 import BeautifulSoup
from .selectors import PRODUCT_CARD, NAME, SALE, PRICE, LINK, STOCK, DISCOUNT
from app.utils.utils import extrair_consola

BASE_URL = "https://mega-mania.com.pt/pt/catalogo/?p=1&f="

def parse_products(html):
    soup = BeautifulSoup(html, "html.parser")
    products = []

    cards = soup.select(PRODUCT_CARD)

    for card in cards:
        try:
            name_tag = card.select_one(NAME)
            name = name_tag.get_text(strip=True)
            console = extrair_consola(name)
            discount_tag = card.select_one(DISCOUNT)
            has_discount = bool(discount_tag)
            price_tag = card.select_one(PRICE)
            sale_tag = card.select_one(SALE)

            price = None
            sale = None

            if sale_tag:
                price = parse_price(sale_tag.get_text(strip=True))
            
                if price_tag:
                    sale = parse_price(price_tag.get_text(strip=True))
            
            else:
                if price_tag:
                    price = parse_price(price_tag.get_text(strip=True))
                elif sale_tag:
                    price = parse_price(sale_tag.get_text(strip=True))

            link_tag = card.select_one(LINK)

            if not console:
                continue

            link = link_tag["href"]
            if link and link.startswith("/"):
                link = "https://mega-mania.com.pt" + link

            in_stock = parse_stock(card)
            if not in_stock:
                continue
            
            name = name_tag.get_text(strip=True)

            image_tag = card.select_one(".produto_lista_imagem img")

            image = None

            if image_tag:
                image = image_tag.get("src")
                
                if image and image.startswith("/"):
                    image = "https://mega-mania.com.pt" + image

            products.append({
                "store": "mega-mania",
                "external_name": name,
                "sale": sale,
                "price": price,
                "has_discount": has_discount,
                "console": console,
                "url": link,
                "image": image,
                "in_stock": in_stock
            })

        except Exception as e:
            print(f"[Mega-Mania Parser] Erro: {e}")

    return products

def parse_price(price_text):
    """
    Ex:
    "59,99 €" → 59.99
    "€39.99" → 39.99
    """
    price_text = price_text.replace("€", "").replace(",", ".").strip()

    if "-" in price_text:
        price_text = price_text.split("-")[0].strip()

    return float(price_text)

def parse_stock(card):

    text = card.get_text(strip=True).lower()

    if "esgotado" in text:
        return False

    return True