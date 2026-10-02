import logging

from bs4 import BeautifulSoup

from app.utils.utils import detetar_plataforma
from scrapers.base.parser_utils import absolute_url, detect_condition, parse_price, parse_release_date, text_of
from .selectors import AVAILABILITY, IMAGE, LINK, NAME, OLD_PRICE, PRICE, PRODUCT_CARD

log = logging.getLogger(__name__)

BASE_URL = "https://www.gamingreplay.com"


def parse_products(html, console=None):
    """
    The games on a category page. Pre-owned copies are in the same list, named "… (Seminovo) PS5";
    pre-orders say "Em Reserva (31-12-2026)" with the release date, and can be bought.
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []

    for card in soup.select(PRODUCT_CARD):
        try:
            name = card.select_one(NAME).get_text(" ", strip=True)
            availability = " ".join(text_of(card.select_one(AVAILABILITY)).split())
            preorder = availability.lower().startswith("em reserva")
            image = card.select_one(IMAGE)

            products.append({
                "store": "gaming_replay",
                "external_name": name,
                "console": detetar_plataforma(name, console),
                "condition": detect_condition(name),
                "price": parse_price(text_of(card.select_one(PRICE))),
                "old_price": parse_price(text_of(card.select_one(OLD_PRICE))),
                "in_stock": "esgotado" not in availability.lower(),
                "is_preorder": preorder,
                "release_date": parse_release_date(availability) if preorder else None,
                "release_date_checked": True,
                "url": absolute_url(BASE_URL, card.select_one(LINK)["href"]),
                "image": absolute_url(BASE_URL, image.get("src")) if image else None,
            })

        except Exception as e:
            log.warning("[Gaming Replay Parser] %s", e)

    return products
