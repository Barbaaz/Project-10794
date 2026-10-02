from urllib.parse import quote_plus

from scrapers.base.base_scraper import BaseScraper
from .parser import parse_products


class PressStartScraper(BaseScraper):
    store_slug = "press_start"
    base_url = "https://www.pressstart.pt"

    catalog_urls = {
        "https://www.pressstart.pt/pt/jogos-ps5/": "PS5",
        "https://www.pressstart.pt/pt/jogos-ps4/": "PS4",
        "https://www.pressstart.pt/pt/jogos-nintendo-switch/": "Switch",
        "https://www.pressstart.pt/pt/jogos-switch-2/": "Switch2",
        "https://www.pressstart.pt/pt/jogos-xbox-series-x/": "XboxSeries",
        "https://www.pressstart.pt/pt/jogos-xbox-one/": "XboxOne",
        "https://www.pressstart.pt/pt/jogos-pc/": "PC",
    }

    def build_search_url(self, query, page):
        return f"{self.base_url}/pt/pesquisar?s={quote_plus(query)}&page={page}"

    def build_page_url(self, url, page):
        return f"{url}?page={page}"

    def parse_listing(self, html, console=None):
        return parse_products(html, console)
