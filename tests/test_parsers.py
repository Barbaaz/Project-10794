"""
Store parsers against saved pages (tests/fixtures). If a store changes its HTML, refresh the
fixture from the live site and see which of these break.
"""
from scrapers.cstech.scraper import CSTechScraper
from scrapers.mega_mania.parser import parse_products as parse_mega_mania
from scrapers.press_start.parser import parse_products as parse_press_start

from datetime import date

from scrapers.press_start.parser import parse_product_page

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


def test_mega_mania_sold_out_pre_order():
    # Limited editions: the button still says PRÉ-ENCOMENDAR, but the box says "Esgotado"
    # (Control Resonant Steelbook Edition PS5, reported 2026-10-02)
    html = """
    <div class="produto_lista MolduraProdutos">
      <div class="produto_lista_imagem"><a href="/pt/produto/9172-control-resonant-steelbook-edition-ps"><img src="/x.jpg"></a></div>
      <div class="produto_lista_titulo"><p><a href="#">CONTROL RESONANT Steelbook Edition PS5</a></p></div>
      <div class="produto_lista_stock_wrapper"><div class="produto_lista_stock_esgotado">Esgotado</div></div>
      <div class="produto_lista_botoes">
        <div class="produto_lista_botoes__bt"><div class="produto_lista_botoes__bt_texto">PRÉ-ENCOMENDAR</div>
          <div class="produto_lista_botoes__bt_preco">69,99€</div></div>
        <div class="produto_lista_botoes__bt produto_lista_botoes__bt_vermelho"><span>Lançamento:</span> 15 Outubro 2026</div>
      </div>
    </div>"""
    [product] = parse_mega_mania(html, "PS5")
    assert product["is_preorder"] is True
    assert product["in_stock"] is False
    assert product["release_date"] == date(2026, 10, 15)


def test_mega_mania_pre_order_and_release_date(fixture_text):
    products = parse_mega_mania(fixture_text("mega_mania_listing.html"), "PS5")
    pre_order = by_name(products, "ACE COMBAT 8")
    assert pre_order["is_preorder"] is True
    assert pre_order["release_date"] == date(2026, 10, 2)    # "Lançamento: 2 Outubro 2026"
    assert by_name(products, "007 FIRST LIGHT")["is_preorder"] is False


def test_press_start_release_date_from_product_page():
    html = "<div>Data prevista de lançamento: 2026-12-31 Ficha técnica Etiqueta PRÉ-RESERVA</div>"
    assert parse_product_page(html)["release_date"] == date(2026, 12, 31)
    assert parse_product_page("<div>Data prevista de lançamento: 06/10/2026</div>")["release_date"] == date(2026, 10, 6)
    assert parse_product_page("<div>Sem data</div>")["release_date"] is None


def product(url, name="Some Game PS5", preorder=True):
    return {"url": url, "external_name": name, "is_preorder": preorder, "release_date": None, "release_date_checked": False}


def test_product_pages_read_only_when_needed():
    from scrapers.press_start.scraper import PressStartScraper

    fetched = []
    scraper = PressStartScraper(fresh_release_urls={"https://x/fresh"},
                                known_detail_urls={"https://x/fresh", "https://x/out"})
    scraper.fetch_product_page = lambda url: fetched.append(url) or {
        "release_date": date(2026, 11, 20), "description": "Conteúdo: estátua", "details": {"Género": "Ação"},
        "images": ["https://x/box.jpg"]}

    products = [
        product("https://x/new"),
        product("https://x/fresh"),                    # date checked lately, description known
        product("https://x/out", preorder=False),     # out already, description known
        product("https://x/new"),                      # same product in a second category
    ]
    scraper.add_product_pages(products)

    assert fetched == ["https://x/new"]     # once, even though it's in two categories
    assert [p["release_date"] for p in products] == [date(2026, 11, 20), None, None, date(2026, 11, 20)]
    assert products[0]["description"] == products[3]["description"] == "Conteúdo: estátua"
    assert products[0]["images"] == ["https://x/box.jpg"] and "images" not in products[1]
    assert products[0]["details_checked"] and "details_checked" not in products[1]


def test_product_pages_special_editions_first():
    from scrapers.press_start.scraper import PressStartScraper

    fetched = []
    scraper = PressStartScraper()
    scraper.max_product_pages = 2
    scraper.fetch_product_page = lambda url: fetched.append(url) or {}
    scraper.add_product_pages([
        product("https://x/standard", "Game PS5", preorder=False),
        product("https://x/preorder", "Other Game PS5"),
        product("https://x/collectors", "Game - Collector's Edition PS5", preorder=False),
    ])
    assert fetched == ["https://x/collectors", "https://x/preorder"]


def test_press_start_product_page():
    from scrapers.press_start.parser import parse_product_page

    html = """
    <div>Data prevista de lançamento: 2026-12-31</div>
    <div id="description"><div class="product-description">
      <p>Conteúdo da Collector's Edition:<br>- Jogo Completo (Download Digital)<br>- Estátua de 38cm</p>
      <p>Embarca numa missão inspiradora.</p></div></div>
    <dl class="data-sheet"><dt>Etiqueta</dt><dd>PRÉ-RESERVA</dd><dt>Género</dt><dd>Ação</dd></dl>"""
    page = parse_product_page(html)
    assert page["release_date"] == date(2026, 12, 31)
    assert page["description"].splitlines() == [
        "Conteúdo da Collector's Edition:", "- Jogo Completo (Download Digital)", "- Estátua de 38cm",
        "Embarca numa missão inspiradora."]
    assert page["details"] == {"Género": "Ação"}
    assert page["images"] == []


def test_press_start_product_photos():
    from scrapers.press_start.parser import parse_product_page

    # Gallery: the cover first, then photos of the box contents; one more photo in the description
    html = """
    <div id="thumb-gallery">
      <img src="https://www.pressstart.pt/1-small_default/x.jpg" data-image-large-src="https://www.pressstart.pt/1-large_default/x.jpg">
      <img src="https://www.pressstart.pt/2-small_default/x.jpg" data-image-large-src="https://www.pressstart.pt/2-large_default/x.jpg">
      <img src="https://www.pressstart.pt/3-small_default/x.jpg" data-image-large-src="https://www.pressstart.pt/3-large_default/x.jpg">
    </div>
    <div id="description"><div class="product-description">
      <p>Conteúdo:</p><img src="/img/cms/conteudo.png"><img src="/img/cms/pegi.svg"></div></div>"""
    assert parse_product_page(html)["images"] == [
        "https://www.pressstart.pt/2-large_default/x.jpg",
        "https://www.pressstart.pt/3-large_default/x.jpg",
        "https://www.pressstart.pt/img/cms/conteudo.png",
    ]


def test_mega_mania_product_photos():
    from scrapers.mega_mania.parser import parse_product_page

    html = """
    <div class="produto-imagem"><a href="/upload/product/9169-tomb.jpeg"><img src="/upload/product/9169-tomb.jpeg"></a></div>
    <div id="descricao-produto"><p>Conteúdo desta edição:</p>
      <div><img src="/upload/photo/1781125850TOMB RAIDER COLLECTORS S.jpg"></div></div>"""
    page = parse_product_page(html)
    assert page["description"] == "Conteúdo desta edição:"
    # the cover isn't in the description; spaces in the file name are encoded
    assert page["images"] == ["https://mega-mania.com.pt/upload/photo/1781125850TOMB%20RAIDER%20COLLECTORS%20S.jpg"]


def test_photo_list():
    from scrapers.base.parser_utils import photo_list

    urls = ["https://a/cover.jpg", "https://a/1.jpg", "https://a/1.jpg", "https://a/icon.svg",
            "data:image/png;base64,xx", None, "https://a/2.webp?v=3"]
    assert photo_list(urls, exclude=["https://a/cover.jpg"]) == ["https://a/1.jpg", "https://a/2.webp?v=3"]
    assert len(photo_list([f"https://a/{n}.jpg" for n in range(30)])) == 12


# --- CSTech (Shopify JSON) -------------------------------------------------

def test_cstech(fixture_json):
    scraper = CSTechScraper()
    items = fixture_json("cstech_products.json")["products"]
    products = [p for p in map(scraper.parse_item, items) if p]

    assert len(products) == 3   # the non-game item is skipped
    assert all(KEYS <= set(p) for p in products)
    assert all(p["details_checked"] for p in products)    # the description comes with the catalogue

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


def test_cstech_photos():
    item = {
        "title": "Game Collector's Edition PS5", "handle": "game-ce", "product_type": "Jogos PS5", "tags": [],
        "images": [{"src": "https://cdn.shopify.com/cover.jpg"}, {"src": "https://cdn.shopify.com/box.jpg"}],
        "body_html": '<p>Inclui:</p><img src="https://cdn.shopify.com/statue.png">',
        "variants": [{"title": "Default Title", "price": "199.99", "compare_at_price": None, "available": True}],
    }
    product = CSTechScraper().parse_item(item)
    assert product["image"] == "https://cdn.shopify.com/cover.jpg"
    assert product["images"] == ["https://cdn.shopify.com/box.jpg", "https://cdn.shopify.com/statue.png"]


def test_darty(fixture_json):
    from core.editions import is_excluded
    from scrapers.darty.scraper import DartyScraper

    collections = fixture_json("darty_collections.json")
    scraper = DartyScraper()
    asked = []
    scraper.fetch_items = lambda path: asked.append(path) or collections[path.split("/")[2]]
    products = scraper.scrape_catalog()

    # pre-orders first (to know them), then the games collection; never the whole store
    assert asked == ["/collections/pre-vendas-gaming/products.json", "/collections/videojogos/products.json"]
    assert all(KEYS <= set(p) for p in products)

    names = sorted(p["external_name"] for p in products)
    assert len(names) == len(set(names)) == 5        # the headset bundle is skipped; GTA VI is in both, once
    assert not any("Headset" in n for n in names)

    wonder = by_name(products, "Super Mario Bros. Wonder")
    assert (wonder["console"], wonder["price"], wonder["in_stock"], wonder["is_preorder"]) == ("Switch", 59.99, True, False)
    assert wonder["details"] is None                  # Darty's "vendor" is the platform, not the publisher
    assert by_name(products, "Donkey Kong")["console"] == "Switch2"
    assert by_name(products, "EA Sports FC 25")["in_stock"] is False

    # pre-orders: only in the pre-orders collection, or in both
    assert by_name(products, "Cities: Skylines II")["is_preorder"] is True
    gta = by_name(products, "GTA VI")
    assert gta["is_preorder"] is True
    assert is_excluded(gta["external_name"])          # "Código de download": not tracked (dropped when saved)


def test_radio_popular(fixture_json):
    from scrapers.radio_popular.parser import parse_products

    html = fixture_json("radio_popular_page.json")["content"]["products"]
    products = parse_products(html, "PS5")
    assert len(products) == 4 and all(KEYS <= set(p) for p in products)

    control = by_name(products, "CONTROL RESONANT")
    assert (control["console"], control["price"], control["condition"]) == ("PS5", 50.99, "new")
    assert (control["is_preorder"], control["in_stock"], control["release_date"]) == (True, True, date(2026, 10, 15))
    assert control["old_price"] is None                       # "PVPR" is the recommended price, not a previous one
    assert control["url"] == "https://www.radiopopular.pt/produto/jogo-ps5-control-resonant"
    assert control["image"].endswith("/140958_0.jpg")         # not the 1x1 placeholder in src

    assert by_name(products, "STAR WAR")["old_price"] == 59.99   # a real crossed-out price


def test_radio_popular_stock_and_condition(fixture_json):
    from scrapers.radio_popular.parser import parse_products

    card = fixture_json("radio_popular_page.json")["content"]["products"].split("</article>")[0] + "</article>"
    in_stock = parse_products(card.replace("schema.org/PreSale", "schema.org/InStock"))[0]
    assert (in_stock["in_stock"], in_stock["is_preorder"]) == (True, False)
    sold_out = parse_products(card.replace("schema.org/PreSale", "schema.org/OutOfStock"))[0]
    assert sold_out["in_stock"] is False
    used = parse_products(card.replace("schema.org/NewCondition", "schema.org/UsedCondition"))[0]
    assert used["condition"] == "used"


def test_radio_popular_paging(fixture_json):
    from scrapers.radio_popular.scraper import RadioPopularScraper

    page = fixture_json("radio_popular_page.json")
    scraper = RadioPopularScraper()
    scraper.categories = {"jogos-ps5-1": "PS5", "jogos-ps5-2": "PS5"}
    asked = []

    def fetch_page(slug, n):
        asked.append((slug, n))
        if slug == "jogos-ps5-2":
            n = 1                                 # a copy of the first category: nothing new
        # "24 games" = 2 pages of 12; each page here gives the fixture's cards under other URLs
        html = page["content"]["products"].replace("/produto/", f"/produto/p{n}-")
        return {"productsTotal": 24, "content": {"products": html}}

    scraper.fetch_page = fetch_page
    products = scraper.scrape_catalog()
    assert asked == [("jogos-ps5-1", 1), ("jogos-ps5-1", 2),   # stops at ceil(24 / 12) = 2 pages
                     ("jogos-ps5-2", 1)]                         # the copy costs one request
    assert len(products) == 8


def test_cstech_ignores_compare_at_price_not_above_price():
    item = {
        "title": "Some Game PS5", "handle": "some-game", "product_type": "Jogos PS5", "tags": [], "images": [],
        "variants": [{"title": "Default Title", "price": "19.99", "compare_at_price": "19.99", "available": True}],
    }
    assert CSTechScraper().parse_item(item)["old_price"] is None
