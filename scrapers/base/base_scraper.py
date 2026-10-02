import logging
import time

from .http_client import HttpClient

log = logging.getLogger(__name__)


class BaseScraper:
    """
    Base for every store scraper.

    Each scraped product is a dict with:
        store, external_name, console, condition ('new' | 'used'),
        price, old_price, in_stock, url, image

    Subclasses set store_slug / base_url and implement:
        parse_listing(html, console=None) -> list of products from one listing page
        build_search_url(query, page)     -> needed for search()
        build_page_url(url, page)         -> needed for scrape_catalog()
        catalog_urls                      -> {category url: console code}
    """

    store_slug = None
    base_url = None
    catalog_urls = {}
    delay = 2           # seconds between requests, to be polite to the store
    max_pages = 200     # safety limit per listing

    def __init__(self, http=None):
        self.http = http or HttpClient()

    # --- implemented by each store -------------------------------------

    def parse_listing(self, html, console=None):
        raise NotImplementedError

    def build_search_url(self, query, page):
        raise NotImplementedError

    def build_page_url(self, url, page):
        raise NotImplementedError

    # --- shared behaviour ----------------------------------------------

    def run(self, query):
        """Kept for app.py: same as search()."""
        return self.search(query)

    def search(self, query):
        return self.crawl(lambda page: self.build_search_url(query, page))

    def scrape_catalog(self):
        """Every game in the store, used by the scheduler to fill the database."""
        products = []

        for url, console in self.catalog_urls.items():
            products.extend(self.crawl(lambda page: self.build_page_url(url, page), console))

        return products

    def crawl(self, make_url, console=None):
        """
        Follow pages until one adds no new products.
        (Asking for a page past the end returns the last page again on these stores,
        so "stop when the page is empty" would never stop.)
        """
        products = []
        seen = set()

        for page in range(1, self.max_pages + 1):
            url = make_url(page)
            log.info("[%s] %s", self.store_slug, url)

            page_products = self.parse_listing(self.http.get_text(url), console)
            new = [p for p in page_products if (p["url"], p["condition"]) not in seen]

            if not new:
                break

            seen.update((p["url"], p["condition"]) for p in new)
            products.extend(new)
            time.sleep(self.delay)

        # Products whose platform we can't tell (accessories, merch...) are not games
        games = [p for p in products if p["console"] and p["price"] is not None]

        log.info("[%s] %d products (%d pages)", self.store_slug, len(games), page)
        return games
