import logging
from datetime import datetime

from scrapers.base.base_scraper import BaseScraper
from scrapers.base.http_client import RequestBudgetExceeded, StoreBlocked
from .parser import parse_product_page, parse_products, parse_sitemap

log = logging.getLogger(__name__)


class TechinnScraper(BaseScraper):
    """
    Techinn (TradeInn's tech store; Spanish company, Portuguese site, prices in €). Its category
    pages show only the first ~96 games (the most popular); "Ver mais" asks Techinn's own search
    service, which we don't use. robots.txt allows the category pages and the sitemap (it forbids
    search, offers, price filters). So each run (user's choice, 2026-10-04):
    - the 4 category pages: the popular games, price fresh every day;
    - the product sitemap (1 request), then up to max_product_pages of the other games' product
      pages, those never read first, then the longest unseen: each is read every ~4 days.
    Products gone from both the sitemap and the listings are the ones deactivated (still_listed).
    With read_hardware, also its 3 console pages (Nintendo, PlayStation, Xbox: consoles only, 2–25
    each, one page each). ~165 requests a run.
    """
    store_slug = "techinn"
    base_url = "https://www.tradeinn.com"

    listing_parser = parse_products

    catalog_urls = {
        "https://www.tradeinn.com/techinn/pt/consolas-jogos-playstation/19292/s": None,
        "https://www.tradeinn.com/techinn/pt/consolas-jogos-nintendo/19291/s": None,
        "https://www.tradeinn.com/techinn/pt/consolas-jogos-xbox/19293/s": None,
        "https://www.tradeinn.com/techinn/pt/jogos-jogos-pc/18390/s": "PC",
    }
    # Consoles (core/hardware.py): the platform from each name (keep_hardware)
    hardware_urls = {f"https://www.tradeinn.com/techinn/pt/{path}/s": (None, "console") for path in (
        "consolas-consolas-nintendo/15858", "consolas-consolas-playstation/15860", "consolas-consolas-xbox/15859")}
    sitemap_url ="https://www.tradeinn.com/techinn/sitemaps/sitemap_productos_1_por_techinn.xml"
    max_product_pages = 150

    def scrape_catalog(self):
        products = {}
        for url, console in self.catalog_urls.items():
            for p in self.parse_listing(self.http.get_text(url), console):
                products.setdefault(p["url"], p)
        log.info("[%s] %d games on the category pages", self.store_slug, len(products))

        listed = parse_sitemap(self.http.get_text(self.sitemap_url))
        self.still_listed = set(listed) | set(products)
        others = [u for u in dict.fromkeys(listed) if u not in products]
        # never read first, then the longest unseen
        others.sort(key=lambda u: self.last_seen.get(u) or datetime.min)
        todo = others[:self.max_product_pages]
        log.info("[%s] %d other games in the sitemap; reading %d product pages", self.store_slug, len(others), len(todo))

        for url in todo:
            try:
                game = parse_product_page(self.http.get_text(url), url)
            except (StoreBlocked, RequestBudgetExceeded):
                raise   # stop now rather than keep knocking
            except Exception as e:
                log.warning("[%s] product page %s: %s", self.store_slug, url, e)
                continue
            if game:
                products.setdefault(game["url"], game)
        for p in products.values():
            p["kind"] = "game"

        hardware = []
        if self.read_hardware:
            for url, (console, page_kind) in self.hardware_urls.items():
                hardware += self.keep_hardware(self.parse_listing(self.http.get_text(url), console), page_kind)
            self.still_listed |= {p["url"] for p in hardware}
            log.info("[%s] %d consoles on the console pages", self.store_slug, len(hardware))
        # first, as in BaseScraper.scrape_catalog: the pipeline keeps the first copy of a URL
        return hardware + list(products.values())
