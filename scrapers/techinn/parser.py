import json
import logging
import re

from bs4 import BeautifulSoup

from app.utils.utils import detetar_plataforma
from scrapers.base.parser_utils import detect_condition, html_to_text, parse_price

log = logging.getLogger(__name__)

# Product URLs in the sitemap that may be games: a brand, then a platform in the slug
# ("/techinn/pt/playstation-ps5-…/141367194/p"; older platforms too: "nintendo-3ds-…", "playstation-ps2-…").
# Techinn sometimes puts a game under the wrong brand ("Playstation PS3 Animal Crossing: Happy Home
# Designer" is a 3DS game): a moderator moves it in /admin
GAME_SLUG = re.compile(r"/techinn/pt/(?:playstation|nintendo|xbox|microsoft|sega)-[^/]*"
                       r"(?:ps[1-5]|playstation-[1-5]|psp|vita|switch|xbox-series|series-[xs]|xbox-one|xbox-360|"
                       r"[23]ds|wii|gamecube|game-boy|gba|n64|snes|nes|dreamcast|saturn|mega-drive)[^/]*/\d+/p$")
# ...but not the controllers, headsets and such those brands also sell (the product page's
# category is checked as well: only "Jogos …" are kept)
NOT_A_GAME = re.compile(
    r"-(?:controle|comando|controlador|joy-con|headset|auscultador|fones?|carregador|cabo|base|capa|volante|"
    r"consola|console|cartao|memoria|suporte|estacao|adaptador|bolsa|pelicula|protetor|amiibo|figura|"
    r"disco-rigido|camara|camera|teclado|rato|dock|grip|alimentador|bateria|caneta|estojo|modulo|vr2?)(?:-|/)")


def _product(name, price, in_stock, url, image, console=None, description=None, details_checked=False):
    return {
        "store": "techinn",
        "external_name": name,
        "console": detetar_plataforma(name, console),
        "condition": detect_condition(name),
        "price": price,
        "old_price": None,          # the store's crossed-out price is never a discount for us
        "in_stock": in_stock,
        "is_preorder": False,
        "release_date": None,
        "url": url,
        "image": image,
        **({"description": description, "details": None, "images": [], "details_checked": True}
           if details_checked else {}),
    }


def parse_products(html, console=None):
    """
    The games on a category page: name, price, link and picture. The first 78–96 only (the rest
    load from Techinn's search service, which we don't use); the listing has no stock mark, and
    the listed games checked on 2026-10-04 were all in stock.
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []
    for card in soup.select("li.product-listing-wrapper"):
        try:
            link = card.select_one("a[href]")
            name = card.select_one(".js-nombre_producto_listado").get_text(" ", strip=True)
            image = card.select_one("img.js-image_list_product")
            products.append(_product(name, parse_price(card.select_one(".js-precio_producto").get_text()), True,
                                     link["href"], image.get("src") if image else None, console))
        except Exception as e:
            log.warning("[Techinn Parser] %s", e)
    return [p for p in products if p["console"]]


def parse_sitemap(xml):
    """The product sitemap's URLs that may be games (on the brands' slugs, accessories left out)."""
    urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
    return [u for u in urls if GAME_SLUG.search(u) and not NOT_A_GAME.search(u)]


def parse_product_page(html, url=None):
    """
    A product page's game, from its schema.org data (price, stock, picture, description), or None
    when it isn't a game (its category doesn't say "Jogos") or its platform can't be told.
    """
    soup = BeautifulSoup(html, "html.parser")
    product = None
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            candidate = item.get("mainEntity") if isinstance(item, dict) else None
            if isinstance(candidate, dict) and candidate.get("@type") == "Product":
                product = candidate
    if not product or "jogos" not in (product.get("category") or "").lower():
        return None

    offers = product.get("offers") or []
    offers = offers if isinstance(offers, list) else [offers]
    offer = next((o for o in offers if "InStock" in (o.get("availability") or "")), offers[0] if offers else {})
    if not offer.get("price"):
        return None
    game = _product(product["name"], parse_price(offer["price"]), "InStock" in (offer.get("availability") or ""),
                    url or product.get("url"), product.get("image"),     # the sitemap's URL: the one still_listed has
                    description=html_to_text(product.get("description")), details_checked=True)
    if "UsedCondition" in (offer.get("itemCondition") or product.get("itemCondition") or ""):
        game["condition"] = "used"
    return game if game["console"] else None
