import logging

from app.utils.utils import extrair_consola
from core.editions import parse_title
from core.hardware import PLATFORMS as HARDWARE_PLATFORMS, kind_of
from .http_client import HttpClient, RequestBudgetExceeded, StoreBlocked

log = logging.getLogger(__name__)


class BaseScraper:
    """
    Base for every store scraper.

    Each scraped product is a dict with:
        store, external_name, console, condition ('new' | 'used'),
        price, old_price, in_stock, url, image,
        is_preorder, release_date (date or None), release_date_checked (date was looked up this run)
    and, when the product page was read this run (or the listing has it, like CSTech):
        description (plain text), details (dict), images (photos besides the cover), details_checked

    Subclasses set store_slug / base_url and:
        listing_parser                    -> parse_products(html, console) from the store's parser.py
        product_page_parser               -> parse_product_page(html), for stores with useful product pages
        build_search_url(query, page)     -> needed for search()
        build_page_url(url, page)         -> needed for scrape_catalog()
        catalog_urls                      -> {category url: console code}
        hardware_urls                     -> {category url: (console code or None, "console" | "accessory")}:
                                             consoles, controllers and headsets (core/hardware.py), read
                                             when read_hardware is on (scheduler/jobs.py HARDWARE_STORES)
    (Stores with another kind of catalogue, like a JSON feed, override scrape_catalog instead.)
    Every product also gets "kind": "game", or the hardware kind.
    """

    store_slug = None
    base_url = None
    catalog_urls = {}
    hardware_urls = {}
    read_hardware = False
    max_pages = 200                  # safety limit per listing
    max_product_pages = 100          # product pages opened per run; the rest wait for the next run
    reads_release_date_from_page = False   # True when the release date is only on the product page
    listing_parser = None
    product_page_parser = None
    # The pause between requests is enforced by HttpClient (see http_client.py)

    def __init__(self, http=None, fresh_release_urls=(), known_detail_urls=(), last_seen=None):
        self.http = http or HttpClient()
        # {url: when a run last saw it}, for stores that read part of their catalogue per run
        self.last_seen = last_seen or {}
        # Those stores set the URLs still on sale (seen or not this run); None: the run saw everything
        self.still_listed = None
        # Pre-orders whose release date was read recently; their product page isn't fetched again
        self.fresh_release_urls = set(fresh_release_urls)
        # Products whose description was already read (read once)
        self.known_detail_urls = set(known_detail_urls)
        self.hardware_left_out = []
        # A store whose hardware costs no extra request (a feed) sorts it anyway while not switched on:
        # what it would keep, to check first (scheduler/jobs.py writes it to logs/hardware_check_<store>.txt)
        self.hardware_preview = None

    # --- implemented by each store -------------------------------------

    def parse_listing(self, html, console=None):
        return type(self).listing_parser(html, console)

    def build_search_url(self, query, page):
        raise NotImplementedError

    def build_page_url(self, url, page):
        raise NotImplementedError

    @property
    def reads_product_pages(self):
        return self.product_page_parser is not None

    def fetch_product_page(self, url):
        """
        {"description": str | None, "details": dict | None, "release_date": date | None, "images": [url]}
        from the product page, for stores with a product_page_parser.
        """
        if not self.reads_product_pages:
            return None
        return type(self).product_page_parser(self.http.get_text(url))

    # --- shared behaviour ----------------------------------------------

    def search(self, query):
        return self.crawl(lambda page: self.build_search_url(query, page))

    def scrape_catalog(self):
        """Every game in the store (and its hardware, with read_hardware), used by the scheduler to fill the database."""
        products = []

        for url, console in self.catalog_urls.items():
            products.extend(self.crawl(lambda page: self.build_page_url(url, page), console))
        for p in products:
            p["kind"] = "game"

        self.add_product_pages(products)     # games only: hardware needs no description or release date
        hardware = []
        if self.read_hardware:
            for url, (console, page_kind) in self.hardware_urls.items():
                hardware.extend(self.keep_hardware(self.crawl(lambda page: self.build_page_url(url, page), console),
                                                   page_kind))
        # first: a store lists some consoles among its games too ("Consola Switch OLED + Mario Wonder"), and
        # the pipeline keeps the first copy of a URL (pipeline/deduplicator.py)
        return hardware + products

    def keep_hardware(self, products, page_kind):
        """The consoles, controllers and headsets of a hardware page, with their kind; the rest
        (small accessories, chairs, other platforms…) left out, kept in hardware_left_out to check."""
        kept = []
        for p in products:
            kind = kind_of(p["external_name"], page_kind)
            # a platform the name says wins over the page's ("Comando Nintendo Switch" on the Switch 2 page)
            named = extrair_consola(p["external_name"])
            console = named if named in HARDWARE_PLATFORMS else p["console"]
            # a console names its platform: retro and mini consoles ("THE SPECTRUM", "Game & Watch") are
            # listed on platforms' pages they don't belong to
            if kind == "console" and named not in HARDWARE_PLATFORMS:
                kind = None
            if kind and console in HARDWARE_PLATFORMS:
                kept.append({**p, "kind": kind, "console": console})
            else:
                self.hardware_left_out.append(p["external_name"])
        return kept

    def needs_release_date(self, p):
        return (self.reads_release_date_from_page and p["is_preorder"] and not p["release_date"]
                and p["url"] not in self.fresh_release_urls)

    def needs_details(self, p):
        return p["url"] not in self.known_detail_urls

    def add_product_pages(self, products):
        """
        Open product pages for what the listing doesn't show: the release date of pre-orders
        (not checked lately) and the description (read once per product). One visit gives both.
        At most max_product_pages per run: special editions first (their description says what
        they include), then pre-orders, then the rest; the others wait for the next runs.
        """
        if not self.reads_product_pages:
            return

        def priority(p):
            special = parse_title(p["external_name"]).phrase != ""
            return (not special, not p["is_preorder"])

        pending = {}
        for p in sorted(products, key=priority):
            if self.needs_release_date(p) or self.needs_details(p):
                pending.setdefault(p["url"], p)
        todo = list(pending)[:self.max_product_pages]
        if todo:
            log.info("[%s] reading %d product pages (%d left for later runs)",
                     self.store_slug, len(todo), len(pending) - len(todo))

        pages = {}
        for url in todo:
            try:
                pages[url] = self.fetch_product_page(url) or {}
            except (StoreBlocked, RequestBudgetExceeded):
                raise   # stop now rather than keep knocking
            except Exception as e:
                log.warning("[%s] product page %s: %s", self.store_slug, url, e)

        # The same product can appear in two categories: fill in every copy
        for p in products:
            page = pages.get(p["url"])
            if page is None:
                continue
            if self.needs_release_date(p):
                p["release_date"] = page.get("release_date")
                p["release_date_checked"] = True
            if self.needs_details(p):
                p["description"] = page.get("description")
                p["details"] = page.get("details")
                p["images"] = page.get("images")
                p["details_checked"] = True

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
