import logging

from bs4 import BeautifulSoup

from app.utils.utils import detetar_plataforma
from scrapers.base.parser_utils import parse_price, parse_release_date, detect_condition, absolute_url, html_to_text
from .selectors import (
    PRODUCT_CARD, NAME, IMAGE, LINK, BUY_BUTTON, BUY_LABEL, PRICE, OLD_PRICE, OUT_OF_STOCK, RELEASE_DATE,
    DESCRIPTION,
)

log = logging.getLogger(__name__)

BASE_URL = "https://mega-mania.com.pt"


def parse_products(html, console=None):
    soup = BeautifulSoup(html, "html.parser")
    products = []

    for card in soup.select(PRODUCT_CARD):
        try:
            name = card.select_one(NAME).get_text(strip=True)

            button = card.select_one(BUY_BUTTON)
            label = text_of(button.select_one(BUY_LABEL)) if button else None
            price = parse_price(text_of(button.select_one(PRICE))) if button else None

            image_tag = card.select_one(IMAGE)

            products.append({
                "store": "mega-mania",
                "external_name": name,
                "console": detetar_plataforma(name, console),
                "condition": detect_condition(label, name),   # the button says "COMPRAR USADO" for used games
                "price": price,
                "old_price": parse_price(text_of(card.select_one(OLD_PRICE))),
                "in_stock": parse_stock(card),
                "is_preorder": "ENCOMENDA" in (label or "").upper(),   # "PRÉ-ENCOMENDAR"
                "release_date": parse_release_date(text_of(card.select_one(RELEASE_DATE))),
                "release_date_checked": True,
                "url": absolute_url(BASE_URL, card.select_one(LINK)["href"]),
                "image": absolute_url(BASE_URL, image_tag.get("src")) if image_tag else None,
            })

        except Exception as e:
            log.warning("[Mega-Mania Parser] Erro: %s", e)

    return products


def parse_product_page(html):
    """Description from a product page (the release date is already on the listing)."""
    tag = BeautifulSoup(html, "html.parser").select_one(DESCRIPTION)
    return {"description": html_to_text(str(tag)) if tag else None, "details": None}


def parse_stock(card):
    # The "esgotado" box is also used for pre-orders ("Pré-encomenda"), which can be bought
    tag = card.select_one(OUT_OF_STOCK)
    return tag is None or "esgotado" not in tag.get_text(strip=True).lower()


def text_of(tag):
    return tag.get_text(strip=True) if tag else None
