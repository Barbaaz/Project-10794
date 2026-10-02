import logging

from bs4 import BeautifulSoup

from app.utils.utils import detetar_plataforma
from scrapers.base.parser_utils import parse_price, detect_condition
from .selectors import PRODUCT_CARD, NAME, IMAGE, PRICE, PRICE_VALUE, OLD_PRICE, LINK, STOCK

log = logging.getLogger(__name__)


def parse_products(html, console=None):
    soup = BeautifulSoup(html, "html.parser")
    products = []

    for card in soup.select(PRODUCT_CARD):
        try:
            name = card.select_one(NAME).get_text(strip=True)
            image_tag = card.select_one(IMAGE)

            # Long names are cut with "..." in the title; the image alt has the full name
            if name.endswith("...") and image_tag and image_tag.get("alt"):
                name = image_tag["alt"].strip()

            image = None
            if image_tag:
                image = image_tag.get("data-full-size-image-url") or image_tag.get("src")

            products.append({
                "store": "press_start",
                "external_name": name,
                "console": detetar_plataforma(name, console),
                "condition": detect_condition(name),
                "price": parse_card_price(card),
                "old_price": parse_price(text_of(card.select_one(OLD_PRICE))),
                "in_stock": parse_stock(card),
                "url": card.select_one(LINK)["href"],
                "image": image,
            })

        except Exception as e:
            log.warning("[PressStart Parser] Erro: %s", e)

    return products


def parse_card_price(card):
    price_tag = card.select_one(PRICE)
    if not price_tag:
        return None

    value_tag = price_tag.select_one(PRICE_VALUE) or (price_tag if price_tag.has_attr("content") else None)
    if value_tag and value_tag.get("content"):
        return parse_price(value_tag["content"])

    return parse_price(price_tag.get_text(strip=True))


def parse_stock(card):
    stock_tag = card.select_one(STOCK)

    if not stock_tag:
        return True

    # low-stock = red light = "add to cart" disabled on the product page
    return "low-stock" not in stock_tag.get("class", [])


def text_of(tag):
    return tag.get_text(strip=True) if tag else None
