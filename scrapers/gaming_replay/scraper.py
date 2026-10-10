from scrapers.base.base_scraper import BaseScraper
from .parser import parse_products


class GamingReplayScraper(BaseScraper):
    """
    Gaming Replay (PrestaShop). Per platform, the "Jogos" category (new games and pre-orders) and
    "Seminovos" (pre-owned copies, named "… (Seminovo) PS5"); a game in both is kept once by the
    pipeline. (The parent "Jogos <platform>" category misses a few games on some platforms.)
    12 games per page: robots.txt forbids the page-size parameter (n=), as well as sorting and
    search, so we only follow ?p=. Checked 2026-10-03: robots.txt allows category pages; the terms
    say nothing against reading the catalogue. A full run is ~110 requests.
    """
    store_slug = "gaming_replay"
    base_url = "https://www.gamingreplay.com"

    listing_parser = parse_products

    catalog_urls = {
        "https://www.gamingreplay.com/pt/2556-jogos-ps5": "PS5",
        "https://www.gamingreplay.com/pt/2290-seminovos-ps5": "PS5",
        "https://www.gamingreplay.com/pt/80-jogos-ps4": "PS4",
        "https://www.gamingreplay.com/pt/114-seminovos-ps4": "PS4",
        "https://www.gamingreplay.com/pt/3175-jogos-nintendo-switch-2": "Switch2",
        "https://www.gamingreplay.com/pt/3178-seminovos-nintendo-switch-2": "Switch2",
        "https://www.gamingreplay.com/pt/230-jogos-nintendo-switch": "Switch",
        "https://www.gamingreplay.com/pt/1542-seminovos-switch": "Switch",
        "https://www.gamingreplay.com/pt/2557-jogos-xbox-series-xs": "XboxSeries",
        "https://www.gamingreplay.com/pt/2361-seminovos-xbox-series-xs": "XboxSeries",
        "https://www.gamingreplay.com/pt/88-jogos-xbox-one": "XboxOne",
        "https://www.gamingreplay.com/pt/115-seminovos-xbox-one": "XboxOne",
        "https://www.gamingreplay.com/pt/48-jogos-pc": "PC",      # boxed games (not "Jogos Digitais": codes)
    }
    # Consoles (core/hardware.py), per platform
    hardware_urls = {f"https://www.gamingreplay.com/pt/{path}": hint for path, hint in {
        "2288-consolas-ps5": ("PS5", "console"),
        "3161-consolas-nintendo-switch-2": ("Switch2", "console"),
        "229-consolas-nintendo-switch": ("Switch", "console"),
    }.items()}

    def build_page_url(self, url, page):
        return url if page == 1 else f"{url}?p={page}"
