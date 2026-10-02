from urllib.parse import quote

from scrapers.base.base_scraper import BaseScraper
from .parser import parse_products, parse_product_page


class MegaManiaScraper(BaseScraper):
    store_slug = "mega-mania"
    base_url = "https://mega-mania.com.pt"

    catalog_urls = {
        "https://mega-mania.com.pt/pt/catalogo/456-ps/457-jogos": "PS5",
        "https://mega-mania.com.pt/pt/catalogo/1-ps/93-jogos": "PS4",
        "https://mega-mania.com.pt/pt/catalogo/5-nintendo/268-jogos/225-nintendo-switch": "Switch",
        "https://mega-mania.com.pt/pt/catalogo/5-nintendo/268-jogos/525-nintendo-switch-2": "Switch2",
        "https://mega-mania.com.pt/pt/catalogo/480-xbox-one-x/481-jogos": "XboxSeries",  # despite the URL, Series X games
        "https://mega-mania.com.pt/pt/catalogo/2-xbox-one/159-jogos": "XboxOne",
        "https://mega-mania.com.pt/pt/catalogo/10-pc/278-jogos": "PC",
    }

    def build_search_url(self, query, page):
        return f"{self.base_url}/pt/catalogo/?p={page}&f={quote(query)}&ppage=50"

    def build_page_url(self, url, page):
        return f"{url}?p={page}&ppage=50"

    def parse_listing(self, html, console=None):
        return parse_products(html, console)

    def fetch_product_page(self, url):
        return parse_product_page(self.http.get_text(url))
