import logging
import math

from scrapers.base.base_scraper import BaseScraper
from .parser import parse_products

log = logging.getLogger(__name__)

AJAX_URL = "https://www.radiopopular.pt/ajax"
PAGE_SIZE = 12   # fixed by the store


class RadioPopularScraper(BaseScraper):
    """
    Rádio Popular shows 12 games per category page and loads the rest by script, with a
    POST to /ajax (method=getProducts, the category and a page number) that answers JSON:
    {"productsTotal": 251, "content": {"products": "<article>…"}}. robots.txt allows it.
    The cards have price, stock, condition and the pre-order release date: no product pages.
    """

    store_slug = "radio_popular"
    base_url = "https://www.radiopopular.pt"

    # Category slug → platform. The site links two slugs for most platforms; a slug whose
    # first page brings nothing new (a copy of another) is skipped after that one request.
    categories = {
        "jogos-ps5-1": "PS5",
        "jogos-ps5-2": "PS5",
        "jogos-ps4": "PS4",
        "jogos-ps4-1": "PS4",
        "jogos-nintendo-switch-2": "Switch2",
        "jogos-nintendo-switch-2-1": "Switch2",
        "jogos-nintendo-switch": "Switch",
        "jogos-nintendo-switch-1": "Switch",
        "jogos-xbox": None,          # Series X|S and One together: told apart by the name
        "jogos-xbox-1": None,
        "jogos-pc": "PC",
        "jogos-pc-2": "PC",
    }

    def scrape_catalog(self):
        products, seen = [], set()

        for slug, console in self.categories.items():
            total = None
            for page in range(1, self.max_pages + 1):
                answer = self.fetch_page(slug, page)
                total = answer.get("productsTotal") or 0
                found = parse_products((answer.get("content") or {}).get("products") or "", console)
                new = [p for p in found if (p["url"], p["condition"]) not in seen]
                seen.update((p["url"], p["condition"]) for p in new)
                products.extend(new)
                if not new or page >= math.ceil(total / PAGE_SIZE):
                    break
            log.info("[%s] %s: %s products, %d pages", self.store_slug, slug, total, page)

        # Products whose platform we can't tell (accessories, merch...) are not games
        games = [p for p in products if p["console"] and p["price"] is not None]
        log.info("[%s] %d products", self.store_slug, len(games))
        return games

    def fetch_page(self, slug, page):
        return self.http.post_json(AJAX_URL, data={
            "method": "getProducts", "page": "categoria", "where": slug, "filters": "",
            "order": "Relevance desc", "pageNumber": page, "updatedFilters": 0, "intentId": "",
        }, headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{self.base_url}/categoria/{slug}"})
