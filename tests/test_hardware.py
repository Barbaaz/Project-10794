"""Which store products are consoles, and how they group (core/hardware.py; consoles only, user 2026-10-07)."""
import pytest

from core.hardware import display_name, hardware_key, kind_of


@pytest.mark.parametrize("name, page, kind", [
    ("Consola PlayStation 5 Slim Digital Edition 1TB", "console", "console"),
    ("Bundle Consola Nintendo Switch 2 + Nintendo Switch Sports Resort + 3 Meses NSO", "console", "console"),
    ("Consola Xbox Series X 1TB + 2 Comandos", "console", "console"),             # a bundle is a console
    ("Nintendo Switch OLED Branca", "console", "console"),                         # console page, no "consola"
    ("Consola PS5 Slim", "accessory", "console"),                                  # a feed: the name says so
    # controllers, wheels, headsets: not any more (user, 2026-10-07), also on a console page
    ("Comando sem fios DualSense Playstation 5 Edição Especial Icon Blue", "console", None),
    ("Volante Logitech G923 + Pedais PS5", "console", None),
    ("Headset Pulse Elite PS5", "console", None),
    ("PlayStation VR2", "console", None),
    ("Joy-Con (L)/(R) Pastel Purple/Green", "console", None),
    # small accessories and merchandise
    ("Bolsa de transporte e protetor de ecrã Nintendo Switch 2 Zelda 40th Anniversary", "console", None),
    ("Suporte vertical para consola PS5 (Slim)", "console", None),
    ("Capa de Silicone PS5 Slim - Dragon Ball Super", "console", None),
    ("Cartão de Memória Expansão 1TB Xbox Series", "accessory", None),
    ("Figura Banpresto One Piece Shanks", "accessory", None),
    ("Comando DualSense", "accessory", None),
])
def test_kind_of(name, page, kind):
    assert kind_of(name, page) == kind


def test_the_same_console_from_two_stores_has_one_key():
    assert hardware_key("Consola PS5 Slim Digital 1TB", "console") == \
        hardware_key("PlayStation 5 Slim Digital Edition 1 TB Consola", "console") == "console:1 digital slim tb"
    assert hardware_key("Consola Nintendo Switch OLED Branca", "console") == hardware_key("Nintendo Switch OLED White", "console")


def test_different_models_stay_apart():
    """Strict: Slim vs Pro, digital vs disc, colours, bundles."""
    assert hardware_key("Consola PS5 Slim Digital", "console") != hardware_key("Consola PS5 Slim", "console")
    assert hardware_key("Consola PS5 Pro", "console") != hardware_key("Consola PS5 Slim", "console")
    assert hardware_key("Switch OLED (Branca)", "console") != hardware_key("Switch OLED (Neon Azul/Vermelho)", "console")
    assert hardware_key("Consola Nintendo Switch 2", "console") != hardware_key("Consola Nintendo Switch 2 + Mario Kart World", "console")


def test_colours_however_written():
    assert hardware_key("Switch OLED Azul/Vermelha Néon", "console") == hardware_key("Switch OLED Blue Red Neon", "console")


def test_the_plain_model_is_standard():
    assert hardware_key("Consola Nintendo Switch 2", "console") == "console:standard"
    assert hardware_key("Consola Sony PlayStation PS5 - Edição Standard", "console") == "console:standard"


def test_display_name():
    assert display_name("Consola PS5 [USADO] (PT)") == "Consola PS5"


def test_a_hardware_page_keeps_consoles_that_name_their_platform():
    """BaseScraper.keep_hardware: the platform the name says; retro / mini consoles listed on other platforms' pages out."""
    from scrapers.base.base_scraper import BaseScraper

    scraper = BaseScraper()
    product = lambda name, console: {"external_name": name, "console": console}
    kept = scraper.keep_hardware([
        product("Consola Nintendo Switch 2", "Switch2"),
        product("Consola Nintendo Switch OLED", "Switch2"),           # the name says Switch
        product("Consola THE SPECTRUM (Retro)", "PS5"),               # listed on the PS5 page: not a PS5
        product("Comando DualSense PS5", "PS5"),
        product("Consola PS3 Slim", "PS3"),                            # an older platform
    ], "console")
    assert [(p["external_name"], p["kind"], p["console"]) for p in kept] == [
        ("Consola Nintendo Switch 2", "console", "Switch2"), ("Consola Nintendo Switch OLED", "console", "Switch")]
    assert scraper.hardware_left_out == ["Consola THE SPECTRUM (Retro)", "Comando DualSense PS5", "Consola PS3 Slim"]


def test_a_shopify_feed_sorts_its_consoles_without_extra_requests():
    """CSTech: its feed has everything; consoles are sorted out of it, kept only when switched on."""
    from scrapers.cstech.scraper import CSTechScraper

    def item(handle, title, product_type):
        return {"handle": handle, "title": title, "product_type": product_type, "vendor": "", "tags": [], "images": [],
                "body_html": "", "variants": [{"price": "59.99", "compare_at_price": None, "available": True}]}

    feed = [item("g", "Astro Bot PS5", "Jogos PS5"), item("c", "Comando DualSense Branco PS5", "Comandos PS5"),
            item("k", "Consola PS5 Slim", "Consolas"), item("x", "Cabo USB-C PS5", "Acessórios PS5"),
            item("f", "Figura Funko Pop Kratos", "Merchandising")]

    class FakeHttp:
        request_count = 0

        def get_json(self, url, params=None):
            self.request_count += 1
            return {"products": feed if params["page"] == 1 else []}

    scraper = CSTechScraper(http=FakeHttp())
    games = scraper.scrape_catalog()
    assert [(p["external_name"], p["kind"]) for p in games] == [("Astro Bot PS5", "game")]
    assert [(p["external_name"], p["kind"]) for p in scraper.hardware_preview] == [("Consola PS5 Slim", "console")]
    assert {"Comando DualSense Branco PS5", "Cabo USB-C PS5"} <= set(scraper.hardware_left_out)

    scraper = CSTechScraper(http=FakeHttp())
    scraper.read_hardware = True
    assert sorted(p["kind"] for p in scraper.scrape_catalog()) == ["console", "game"]
    assert scraper.http.request_count == 2          # the same feed pages as before
