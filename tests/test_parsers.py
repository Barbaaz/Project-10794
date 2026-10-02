"""
Store parsers against saved pages (tests/fixtures). If a store changes its HTML, refresh the
fixture from the live site and see which of these break.
"""
from scrapers.cstech.scraper import CSTechScraper
from scrapers.mega_mania.parser import parse_products as parse_mega_mania
from scrapers.press_start.parser import parse_products as parse_press_start

from datetime import date

from scrapers.press_start.parser import parse_release_date_page

KEYS = {"store", "external_name", "console", "condition", "price", "old_price", "in_stock", "url", "image",
        "is_preorder", "release_date", "release_date_checked"}


def by_name(products, text):
    return next(p for p in products if text in p["external_name"])


# --- Press Start ---------------------------------------------------------

def test_press_start(fixture_text):
    products = parse_press_start(fixture_text("press_start_listing.html"), "PS5")

    assert len(products) == 4
    assert all(set(p) == KEYS for p in products)
    assert all(p["url"].startswith("https://www.pressstart.pt/") for p in products)

    normal = by_name(products, "Naruto")
    assert (normal["price"], normal["old_price"], normal["in_stock"], normal["condition"]) == (29.99, None, True, "new")

    on_sale = by_name(products, "Dance Dance")
    assert (on_sale["price"], on_sale["old_price"]) == (2.09, 2.99)

    # red "low-stock" light = add to cart disabled = sold out
    assert by_name(products, "Far Cry 3")["in_stock"] is False
    assert by_name(products, "Lego Star Wars")["condition"] == "used"


def test_press_start_platform_from_name_when_no_category(fixture_text):
    products = parse_press_start(fixture_text("press_start_listing.html"))
    assert by_name(products, "Naruto")["console"] == "PS5"
    assert by_name(products, "Far Cry 3")["console"] == "PS3"
    assert by_name(products, "Dance Dance")["console"] is None   # Wii: not tracked yet


def test_press_start_uses_image_alt_for_cut_names():
    html = """
    <article class="product-miniature js-product-miniature">
      <a class="thumbnail product-thumbnail" href="https://www.pressstart.pt/pt/x.html">
        <img src="x.jpg" alt="Teenage Mutant Ninja Turtles: Splintered Fate - Deluxe Edition PS5"></a>
      <div class="product-title"><a href="#">Teenage Mutant Ninja Turtles:...</a></div>
      <div class="product-price-and-shipping"><span class="price"><span itemprop="price" content="39.99">39,99 €</span></span></div>
    </article>"""
    [product] = parse_press_start(html, "PS5")
    assert product["external_name"] == "Teenage Mutant Ninja Turtles: Splintered Fate - Deluxe Edition PS5"
    assert product["price"] == 39.99


# --- Mega Mania ----------------------------------------------------------

def test_mega_mania(fixture_text):
    products = parse_mega_mania(fixture_text("mega_mania_listing.html"), "PS5")

    assert len(products) == 5
    assert all(set(p) == KEYS for p in products)
    assert all(p["url"].startswith("https://mega-mania.com.pt/pt/produto/") for p in products)
    assert all(p["image"].startswith("https://mega-mania.com.pt/") for p in products)

    on_sale = by_name(products, "007 FIRST LIGHT")
    assert (on_sale["price"], on_sale["old_price"]) == (49.99, 59.99)

    assert by_name(products, "A PLAGUE TALE")["in_stock"] is False
    # the buy button says "COMPRAR USADO"
    assert by_name(products, "AMONG ASHES")["condition"] == "used"


def test_mega_mania_pre_order_is_in_stock(fixture_text):
    # Pre-orders use the same "esgotado" box as sold-out games, with the text "Pré-encomenda"
    products = parse_mega_mania(fixture_text("mega_mania_listing.html"), "PS5")
    assert by_name(products, "ACE COMBAT 8")["in_stock"] is True


def test_mega_mania_pre_order_and_release_date(fixture_text):
    products = parse_mega_mania(fixture_text("mega_mania_listing.html"), "PS5")
    pre_order = by_name(products, "ACE COMBAT 8")
    assert pre_order["is_preorder"] is True
    assert pre_order["release_date"] == date(2026, 10, 2)    # "Lançamento: 2 Outubro 2026"
    assert by_name(products, "007 FIRST LIGHT")["is_preorder"] is False


def test_press_start_release_date_from_product_page():
    html = "<div>Data prevista de lançamento: 2026-12-31 Ficha técnica Etiqueta PRÉ-RESERVA</div>"
    assert parse_release_date_page(html) == date(2026, 12, 31)
    assert parse_release_date_page("<div>Data prevista de lançamento: 06/10/2026</div>") == date(2026, 10, 6)
    assert parse_release_date_page("<div>Sem data</div>") is None


def test_press_start_release_dates_only_fetched_when_needed():
    from scrapers.press_start.scraper import PressStartScraper

    fetched = []
    scraper = PressStartScraper(fresh_release_urls={"https://x/fresh"})
    scraper.fetch_release_date = lambda url: fetched.append(url) or date(2026, 11, 20)

    products = [
        {"url": "https://x/new", "is_preorder": True, "release_date": None, "release_date_checked": False},
        {"url": "https://x/fresh", "is_preorder": True, "release_date": None, "release_date_checked": False},
        {"url": "https://x/out", "is_preorder": False, "release_date": None, "release_date_checked": False},
        {"url": "https://x/new", "is_preorder": True, "release_date": None, "release_date_checked": False},
    ]
    scraper.add_release_dates(products)

    assert fetched == ["https://x/new"]     # once, even though it's in two categories
    assert [p["release_date"] for p in products] == [date(2026, 11, 20), None, None, date(2026, 11, 20)]
    assert products[0]["release_date_checked"] and products[3]["release_date_checked"]


# --- CSTech (Shopify JSON) -------------------------------------------------

def test_cstech(fixture_json):
    scraper = CSTechScraper()
    items = fixture_json("cstech_products.json")["products"]
    products = [p for p in map(scraper.parse_item, items) if p]

    assert len(products) == 3   # the non-game item is skipped
    assert all(set(p) == KEYS for p in products)

    dune = by_name(products, "Dune")
    assert (dune["price"], dune["old_price"], dune["in_stock"]) == (44.89, 49.99, True)
    assert dune["url"] == "https://cstech.store/products/dune-awakening-day-one-edition-ps5"

    assert by_name(products, "Silent Hill")["in_stock"] is False

    # one variant per region: in stock if any region is available
    yakuza = by_name(products, "Yakuza")
    assert (yakuza["console"], yakuza["in_stock"], yakuza["price"]) == ("PC", True, 69.99)


def test_cstech_pre_order_tag():
    item = {
        "title": "Until Dawn 2 PS5", "handle": "until-dawn-2-ps5", "product_type": "Jogos PS5",
        "tags": ["Jogos PS5", "pre-venda", "pre-venda PS5"], "images": [],
        "variants": [{"title": "Default Title", "price": "41.99", "compare_at_price": None, "available": True}],
    }
    product = CSTechScraper().parse_item(item)
    assert product["is_preorder"] is True
    assert product["release_date"] is None


def test_cstech_ignores_compare_at_price_not_above_price():
    item = {
        "title": "Some Game PS5", "handle": "some-game", "product_type": "Jogos PS5", "tags": [], "images": [],
        "variants": [{"title": "Default Title", "price": "19.99", "compare_at_price": "19.99", "available": True}],
    }
    assert CSTechScraper().parse_item(item)["old_price"] is None
