import logging

from bs4 import BeautifulSoup

from app.utils.utils import detetar_plataforma
from scrapers.base.parser_utils import parse_price, parse_release_date, detect_condition
from .selectors import CARD, NAME, LINK, IMAGE, PRICE, OLD_PRICE, AVAILABILITY, CONDITION, PRESALE_DATE

log = logging.getLogger(__name__)

# schema.org availability values that mean it can't be bought now
NOT_AVAILABLE = {"OutOfStock", "SoldOut", "Discontinued"}
PRE_ORDER = {"PreSale", "PreOrder"}


def parse_products(html, console=None):
    """Product cards of one listing page (the "products" HTML of the /ajax answer)."""
    soup = BeautifulSoup(html, "html.parser")
    products = []

    for card in soup.select(CARD):
        try:
            name = card.select_one(NAME)["content"].strip()
            availability = schema_value(card.select_one(AVAILABILITY))
            condition = schema_value(card.select_one(CONDITION))
            image = card.select_one(IMAGE)
            date = card.select_one(PRESALE_DATE)

            products.append({
                "store": "radio_popular",
                "external_name": name,
                "console": detetar_plataforma(name, console),
                "condition": "used" if condition == "UsedCondition" else detect_condition(name),
                "price": parse_price(card.select_one(PRICE)["content"]),
                "old_price": crossed_out_price(card.select_one(OLD_PRICE)),
                "in_stock": availability not in NOT_AVAILABLE,
                "is_preorder": availability in PRE_ORDER,
                "release_date": parse_release_date(date.get_text(" ", strip=True)) if date else None,
                "release_date_checked": True,
                "url": card.select_one(LINK)["href"],
                "image": image.get("content") if image else None,
            })

        except Exception as e:
            log.warning("[Radio Popular Parser] Erro: %s", e)

    return products


def schema_value(meta):
    """ "http://schema.org/PreSale" → "PreSale" """
    return meta["content"].rsplit("/", 1)[-1] if meta and meta.get("content") else None


def crossed_out_price(tag):
    """The store's crossed-out price; None for "PVPR" (the recommended retail price, not a previous price)."""
    if not tag or "PVPR" in tag.get_text() or "strike" not in tag.get("class", []):
        return None
    return parse_price(tag.get_text("", strip=True))
