import logging

from .http_client import HttpClient, RequestBudgetExceeded, StoreBlocked

log = logging.getLogger(__name__)


class BaseScraper:
    """
    Base for every store scraper.

    Each scraped product is a dict with:
        store, external_name, console, condition ('new' | 'used'),
        price, old_price, in_stock, url, image,
        is_preorder, release_date (date or None), release_date_checked (date was looked up this run)

    Subclasses set store_slug / base_url and implement:
        parse_listing(html, console=None) -> list of products from one listing page
        build_search_url(query, page)     -> needed for search()
        build_page_url(url, page)         -> needed for scrape_catalog()
        catalog_urls                      -> {category url: console code}
    """

    store_slug = None
    base_url = None
    catalog_urls = {}
    max_pages = 200                  # safety limit per listing
    max_release_date_lookups = 50    # product pages opened per run; the rest wait for the next run
    # The pause between requests is enforced by HttpClient (see http_client.py)

    def __init__(self, http=None, fresh_release_urls=()):
        self.http = http or HttpClient()
        # Pre-orders whose release date was read recently; their product page isn't fetched again
        self.fresh_release_urls = set(fresh_release_urls)

    # --- implemented by each store -------------------------------------

    def parse_listing(self, html, console=None):
        raise NotImplementedError

    def build_search_url(self, query, page):
        raise NotImplementedError

    def build_page_url(self, url, page):
        raise NotImplementedError

    def fetch_release_date(self, url):
        """Stores that only show the release date on the product page override this."""
        return None

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

        self.add_release_dates(products)
        return products

    def add_release_dates(self, products):
        """Open the product page of pre-orders whose date we don't have or haven't checked lately."""
        if type(self).fetch_release_date is BaseScraper.fetch_release_date:
            return

        pending = {p["url"]: p for p in products
                   if p["is_preorder"] and not p["release_date"] and p["url"] not in self.fresh_release_urls}
        todo = dict(list(pending.items())[:self.max_release_date_lookups])
        if todo:
            log.info("[%s] reading release dates of %d pre-orders (%d left for later runs)",
                     self.store_slug, len(todo), len(pending) - len(todo))

        for url, product in todo.items():
            try:
                product["release_date"] = self.fetch_release_date(url)
                product["release_date_checked"] = True
            except (StoreBlocked, RequestBudgetExceeded):
                raise   # stop now rather than keep knocking
            except Exception as e:
                log.warning("[%s] release date of %s: %s", self.store_slug, url, e)

        # The same product can appear in two categories
        for p in products:
            if p["url"] in todo:
                p["release_date"] = todo[p["url"]]["release_date"]
                p["release_date_checked"] = todo[p["url"]]["release_date_checked"]

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

        # Products whose platform we can't tell (accessories, merch...) are not games
        games = [p for p in products if p["console"] and p["price"] is not None]

        log.info("[%s] %d products (%d pages)", self.store_slug, len(games), page)
        return games
