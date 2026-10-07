from urllib.parse import quote_plus

from scrapers.base.base_scraper import BaseScraper
from .parser import parse_products, parse_product_page


class PressStartScraper(BaseScraper):
    store_slug = "press_start"
    base_url = "https://www.pressstart.pt"

    listing_parser = parse_products
    product_page_parser = parse_product_page
    reads_release_date_from_page = True   # pre-order dates are only on the product page

    catalog_urls = {
        "https://www.pressstart.pt/pt/jogos-ps5/": "PS5",
        "https://www.pressstart.pt/pt/jogos-ps4/": "PS4",
        "https://www.pressstart.pt/pt/jogos-nintendo-switch/": "Switch",
        "https://www.pressstart.pt/pt/jogos-switch-2/": "Switch2",
        "https://www.pressstart.pt/pt/jogos-xbox-series-x/": "XboxSeries",
        "https://www.pressstart.pt/pt/jogos-xbox-one/": "XboxOne",
        "https://www.pressstart.pt/pt/jogos-pc/": "PC",
    }
    # Consoles (core/hardware.py); the platform from the name where a page has several
    hardware_urls = {
        "https://www.pressstart.pt/pt/consolas/": (None, "console"),
        "https://www.pressstart.pt/pt/consolas-nintendo-switch-2/": ("Switch2", "console"),
        "https://www.pressstart.pt/pt/consolas-nintendo-switch/": ("Switch", "console"),
    }

    def build_search_url(self, query, page):
        return f"{self.base_url}/pt/pesquisar?s={quote_plus(query)}&page={page}"

    def build_page_url(self, url, page):
        return f"{url}?page={page}"
