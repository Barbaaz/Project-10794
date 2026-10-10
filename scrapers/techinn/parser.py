import json
import logging
import re

from bs4 import BeautifulSoup

from app.utils.utils import PLATFORM_PATTERNS, detetar_plataforma, extrair_consola
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


# Techinn's names start with the brand, often before the platform ("XBOX Xbox One Rage 2", "Nintendo
# Nintendo Switch Neva", "Pc Games PC Endless Space 2") and end with the box's language ("(FR/Multi
# in Game)", "(UK/AR)", "… IT", "…-PL"): the same game for us
PC_GAMES = re.compile(r"^pc\s+games\s+", re.IGNORECASE)
BRAND = re.compile(r"^(?:playstation|nintendo|xbox|microsoft)\s+", re.IGNORECASE)
LANGUAGE_TAG = re.compile(r"\s*\((?:[A-Z]{2,4}(?:[/-][^)]*)?|[a-z]{2}/multi[^)]*)\)", re.IGNORECASE)
LANGUAGES = r"(?:IT|ITA|ENG|EN|PL|POL|FR|DE|ES|NL|UK|PT|AR|EU)"
LANGUAGE_END = re.compile(rf"[\s-]+{LANGUAGES}(?:/{LANGUAGES})*$")
# "… Import", "… IMP", "(Portrait Cover) Import USA": a bracketed tag (core/editions.py: "Import US" an
# edition of its own, a plain "(Import)" ignored)
IMPORT = re.compile(r"\s*\(?\b(?:[Ii]mport(?:ed)?|IMPORT|IMP)\b(\s+USA?\b)?\)?\s*$")
# The platforms the name-normaliser doesn't remove (core/normalizer.py knows the current ones):
# taken off the front of the name once the platform is known ("Xbox 360 Batman" → "Batman")
OLDER_PLATFORMS = [(code, re.compile(rf"^(?:{pattern})\s*", re.IGNORECASE)) for code, pattern in PLATFORM_PATTERNS
                   if code not in {"Switch2", "Switch", "PS5", "PS4", "PS3", "XboxSeries", "XboxOne", "Xbox", "PC"}]
# Console names (its console pages, 2026-10-10): the platform repeated at the end ("Nintendo Switch OLED
# JP switch"), the Portal without its brand ("Jogador remoto PS Portal"), an Xbox without "Xbox"
# ("Console Series S 1TB")
PLATFORM_AT_END = re.compile(r"(?<=\S)\s+switch$")
PS_PORTAL = re.compile(r"^(?:playstation\s+)?(?:jogador\s+remoto\s+)?ps\s+portal\b", re.IGNORECASE)
SERIES_WITHOUT_XBOX = re.compile(r"^console\s+series\b", re.IGNORECASE)
EDITION_AFTER_HYPHEN =re.compile(r"(?<=\w)-(?=(?:Special|Deluxe|Gold|Premium|Ultimate|Complete|Collector|Limited|"
                                  r"Standard|Launch|Day|PlayStation\s+Hits)\b)", re.IGNORECASE)


def clean_name(name):
    """
    "XBOX Xbox One Just Cause 3 (Gold Edition) (DE/Multi in Game)" → "Xbox One Just Cause 3 (Gold Edition)";
    the brand stays when the platform needs it ("XBOX 360 Call of Duty").
    """
    name = " ".join(name.replace("´", "'").split())
    name = PC_GAMES.sub("PC ", name)
    name = re.sub(r"^PC\s+PC\s+", "PC ", name, flags=re.IGNORECASE)
    rest = BRAND.sub("", name, count=1)
    if rest != name and extrair_consola(rest):
        name = rest
    name = re.sub(r"^xbox\s+one\s*/\s*(?!\s*(?:xbox|series))", "Xbox One ", name, flags=re.IGNORECASE)   # "Xbox One/ FIFA®21"
    name = re.sub(r"\bsmart\s+delivery\b\s*", "", name, flags=re.IGNORECASE)
    if len(re.findall(r"\bswitch\b", name, re.IGNORECASE)) > 1:
        name = PLATFORM_AT_END.sub("", name)
    name = PS_PORTAL.sub("Consola PlayStation Portal PS5", name)
    name = SERIES_WITHOUT_XBOX.sub("Console Xbox Series", name)
    name = LANGUAGE_TAG.sub("", name)
    for _ in range(2):              # "… IMP EU": the language, then the import mark
        name = LANGUAGE_END.sub("", name.strip())
        name = IMPORT.sub(lambda m: " (Import USA)" if m.group(1) else " (Import)", name)
    return EDITION_AFTER_HYPHEN.sub(" ", name).strip()


def _product(name, price, in_stock, url, image, console=None, description=None, details_checked=False):
    name = clean_name(name)
    console = detetar_plataforma(name, console)
    for code, at_start in OLDER_PLATFORMS:
        if code == console:
            name = at_start.sub("", name, count=1)
    return {
        "store": "techinn",
        "external_name": name,
        "console": console,
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
