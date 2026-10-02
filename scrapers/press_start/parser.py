import logging
import re

from bs4 import BeautifulSoup

from app.utils.utils import detetar_plataforma
from scrapers.base.parser_utils import parse_price, parse_release_date, detect_condition, html_to_text
from .selectors import (
    PRODUCT_CARD, NAME, IMAGE, PRICE, PRICE_VALUE, OLD_PRICE, LINK, STOCK, PREORDER_FLAG,
    DESCRIPTION, DESCRIPTION_SHORT,
)

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
                "is_preorder": card.select_one(PREORDER_FLAG) is not None,
                "release_date": None,             # filled from the product page, see PressStartScraper
                "release_date_checked": False,
                "url": card.select_one(LINK)["href"],
                "image": image,
            })

        except Exception as e:
            log.warning("[PressStart Parser] Erro: %s", e)

    return products


def parse_release_date_page(html):
    """Release date from a product page: "Data prevista de lançamento: 2026-12-31"."""
    return parse_product_page(html)["release_date"]


def parse_product_page(html):
    """
    From a product page: release date ("Data prevista de lançamento: 2026-12-31"),
    description (what a special edition includes is usually at the top) and the data sheet.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    match = re.search(r"Data prevista de lan[çc]amento:\s*([\d/-]+)", text, re.IGNORECASE)

    description = soup.select_one(DESCRIPTION) or soup.select_one(DESCRIPTION_SHORT)

    # Data sheet ("Ficha técnica"): <dt>Género</dt><dd>Aventura</dd>; "Etiqueta" is just the promo label
    details = {}
    for dt in soup.select(".data-sheet dt"):
        dd = dt.find_next_sibling("dd")
        key, value = dt.get_text(" ", strip=True), dd.get_text(" ", strip=True) if dd else ""
        if key and value and key.lower() != "etiqueta":
            details[key] = value

    return {
        "release_date": parse_release_date(match.group(1)) if match else None,
        "description": html_to_text(str(description)) if description else None,
        "details": details or None,
    }


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
