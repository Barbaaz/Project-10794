from bs4 import BeautifulSoup
from .selectors import PRODUCT_CARD, NAME, SALE, PRICE, LINK, STOCK, DISCOUNT
from app.utils.utils import extrair_consola

BASE_URL = "https://www.pressstart.pt/pt/index.php?fc=module&module=leoproductsearch&controller=productsearch&leoproductsearch_static_token=658541fb9c2614f7870540d8c712d5a0&cate=&search_query="

def parse_products(html):
    soup = BeautifulSoup(html, "html.parser")
    products = []

    cards = soup.select(PRODUCT_CARD)

    for card in cards:
        try:
            name_tag = card.select_one(NAME)
            name = name_tag.get_text(strip=True)
            discount_tag = card.select_one(DISCOUNT)
            has_discount = bool(discount_tag)
            price_tag = card.select_one(PRICE)
            sale_tag = card.select_one(SALE)
            console = extrair_consola(name)
            image_tag = card.select_one(".thumbnail img")
            link_tag = card.select_one(LINK)
            link = link_tag["href"]
            stock_tag = card.select_one(STOCK)

            price = None
            sale = None

            if has_discount:
                if sale_tag:
                    price = parse_price(sale_tag.get_text(strip=True))
                
                if price_tag:
                    sale = parse_price(price_tag.get_text(strip=True))
            
            else:
                if price_tag:
                    price = parse_price(price_tag.get_text(strip=True))
                elif sale_tag:
                    price = parse_price(sale_tag.get_text(strip=True))

            in_stock = True

            if stock_tag:
                classes = stock_tag.get("class", [])

                if any('low-stock' in c for c in classes):
                    in_stock = False

            if not console:
                continue

            in_stock = parse_stock(card)
            if not in_stock:
                continue

            image = None

            if image_tag:
                image = image_tag.get("data-full-size-image-url") or image_tag.get("src")

            products.append({
                "store": "press_start",
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
            print(f"[PressStart Parser] Erro: {e}")

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
    stock_tag = card.select_one(STOCK)

    if not stock_tag:
        return True
    
    classes = stock_tag.get('class', [])

    if 'low-stock' in classes:
        return False
    
    return True