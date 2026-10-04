"""Techinn: its category page, sitemap and product pages (samples cut from the pages saved 2026-10-04),
and which product pages a run reads."""
import json
from datetime import datetime

from scrapers.techinn.parser import parse_product_page, parse_products, parse_sitemap
from scrapers.techinn.scraper import TechinnScraper

BASE = "https://www.tradeinn.com/techinn/pt"


def card(slug, number, name, price):
    return f"""
    <li onmouseenter="mouseenterProductList(this)" class="product-listing-wrapper js-hover-producto pointer">
      <a href="{BASE}/{slug}/{number}/p" title="{name}">
        <div class="listado-foto__mainfoto"><img loading="lazy" alt="{slug}" class="js-image_list_product"
             src="https://www.tradeinn.com/h/14136/{number}/{slug}.webp"></div>
        <div class="listado-txt">
          <h3 class="txt-base js-nombre_producto_listado">{name}</h3>
          <p class="txt-base txt__select txt__bold js-precio_producto -novisibility"> {price} €</p>
        </div>
      </a>
    </li>"""


LISTING = "<main><ul>" + "".join([
    card("playstation-ps5-bomb-rush-cyberfunk", 141367194, "Playstation PS5 Bomb Rush Cyberfunk", "12.49"),
    card("playstation-ps2-pro-evolution-soccer-4-platinum-pes-4", 141895641, "Playstation PS2 Pro Evolution Soccer 4 Platinum PES 4", "9.99"),
    card("playstation-pulse-explore", 140000001, "Playstation Pulse Explore", "199.99"),     # no platform: not a game
]) + "</ul></main>"


def product_page(name, category="Consolas Jogos Playstation", availability="InStock", price="12.49", number=141367194):
    data = {"@context": "https://schema.org", "@type": "WebPage", "mainEntity": {
        "@type": "Product", "name": name, "sku": str(number), "url": f"{BASE}/x/{number}/p", "category": category,
        "image": f"https://www.tradeinn.com/f/14136/{number}/x.webp", "description": "<p>Das mentes da Team Reptile…</p>",
        "itemCondition": "https://schema.org/NewCondition",
        "offers": [{"@type": "Offer", "size": "PAL", "priceCurrency": "EUR", "price": price,
                    "availability": f"https://schema.org/{availability}"}]}}
    organization = {"@context": "https://schema.org", "@type": ["Organization"], "name": "Techinn"}
    return (f'<html><head><script type="application/ld+json">{json.dumps(organization)}</script>'
            f'<script type="application/ld+json">{json.dumps(data)}</script></head><body><p id="js-precio"></p></body></html>')


def test_category_page():
    games = parse_products(LISTING)
    assert [(g["external_name"], g["console"], g["price"], g["in_stock"]) for g in games] == [
        ("PS5 Bomb Rush Cyberfunk", "PS5", 12.49, True),
        ("Pro Evolution Soccer 4 Platinum PES 4", "PS2", 9.99, True),    # older platforms too (their name taken off)
    ]
    assert games[0]["url"] == f"{BASE}/playstation-ps5-bomb-rush-cyberfunk/141367194/p" and games[0]["old_price"] is None


def test_names_lose_the_brand_and_the_box_language():
    """Techinn's names, as found on 2026-10-04, against what the other stores call the game."""
    from core.editions import is_excluded, parse_title
    from scrapers.techinn.parser import _product

    def title(raw, console=None):
        p = _product(raw, 1.0, True, "u", None, console)
        t = parse_title(p["external_name"])
        return p["console"], t.game_title, t.edition_name

    assert title("XBOX Xbox One Just Cause 3 (Gold Edition) (DE/Multi in Game)") == ("XboxOne", "Just Cause 3", "Gold Edition")
    assert title("Nintendo Nintendo Switch Neva") == ("Switch", "Neva", "Standard")
    assert title("Pc Games PC Endless Space 2", "PC") == ("PC", "Endless Space 2", "Standard")
    assert title("XBOX 360 Call of Duty Modern Warfare 2 Hardened Edition") == ("Xbox360", "Call of Duty Modern Warfare 2", "Hardened Edition")
    assert title("XBOX Xbox One/Xbox Series X Persona 5 Tactica IT") == ("XboxSeries", "Persona 5 Tactica", "Standard")
    assert title("XBOX Smart Delivery Wreckreation")[1] == "Wreckreation"
    assert title("Playstation PS3 Metal Gear Rising: Revengeance IMP UK")[1:] == ("Metal Gear Rising: Revengeance", "Standard")
    assert title("Playstation PS4 Middle Earth Shadow of War IMP EU")[1] == "Middle Earth Shadow of War"
    assert title("Nintendo Switch Castlevania Dominus Collection (Portrait Cover) (Import USA)")[2] == "Standard · Import US"
    assert title("Pc Games PC The Chant-Limited Edition-EN/PL", "PC")[1:] == ("The Chant", "Limited Edition")
    assert title("Playstation PS4 Journey (Collector´s Edition)")[1:] == ("Journey", "Collector's Edition")
    assert title("Nintendo Switch Imp of the Sun")[1] == "Imp of the Sun"            # "Imp" in a title stays
    assert title("Nintendo Wii U Mario Kart 8") == ("WiiU", "Mario Kart 8", "Standard")
    assert is_excluded(_product("Nintendo Switch Red Dead Redemption CIAB", 1.0, True, "u", None)["external_name"])


def test_sitemap_keeps_the_games():
    xml = "<urlset>" + "".join(f"<url><loc>{BASE}/{slug}/1/p</loc></url>" for slug in (
        "playstation-ps5-nba-2k26", "nintendo-nintendo-switch-2-mario-tennis-fever", "nintendo-3ds-shin-megami-tensei",
        "playstation-controle-sem-fio-ps5-god-of-war", "nintendo-amiibo-zelda-ganondorf", "xbox-fones-de-ouvido-sem-fio",
        "jogos-cadeira-gaming-ps5")) + "</urlset>"
    assert [u.split("/pt/")[1] for u in parse_sitemap(xml)] == [
        "playstation-ps5-nba-2k26/1/p", "nintendo-nintendo-switch-2-mario-tennis-fever/1/p", "nintendo-3ds-shin-megami-tensei/1/p"]


def test_product_page():
    game = parse_product_page(product_page("Playstation PS5 Bomb Rush Cyberfunk"))
    assert (game["console"], game["price"], game["in_stock"], game["condition"]) == ("PS5", 12.49, True, "new")
    assert game["description"].startswith("Das mentes") and game["details_checked"]
    assert parse_product_page(product_page("Playstation PS5 NBA 2K26", availability="OutOfStock"))["in_stock"] is False
    assert parse_product_page(product_page("Playstation Pulse Explore", category="Consolas Acessórios Playstation")) is None


class FakeHttp:
    def __init__(self, pages):
        self.pages, self.asked, self.request_count = pages, [], 0

    def get_text(self, url):
        self.asked.append(url)
        self.request_count += 1
        return self.pages.get(url, "<html></html>")


def test_a_run_reads_the_listings_then_the_longest_unseen_product_pages():
    others = [f"{BASE}/playstation-ps5-game-{n}/{n}/p" for n in range(1, 6)]
    sitemap = "<urlset>" + "".join(f"<loc>{u}</loc>" for u in others) + "</urlset>"
    pages = {TechinnScraper.sitemap_url: sitemap, f"{BASE}/consolas-jogos-playstation/19292/s": LISTING}
    pages.update({u: product_page(f"Playstation PS5 Game {n}", number=n) for n, u in enumerate(others, 1)})
    seen = {others[0]: datetime(2026, 10, 3), others[1]: datetime(2026, 10, 1), others[2]: datetime(2026, 10, 2)}
    scraper = TechinnScraper(http=FakeHttp(pages), last_seen=seen)
    scraper.max_product_pages = 3

    games = scraper.scrape_catalog()
    read = [u for u in scraper.http.asked if u in others]
    assert read == [others[3], others[4], others[1]]        # never seen first, then the longest unseen
    assert len(games) == 2 + 3                              # the listing's two games + three product pages
    assert scraper.still_listed == set(others) | {g["url"] for g in parse_products(LISTING)}
    assert {g["url"] for g in games} <= scraper.still_listed      # what was read is never deactivated
