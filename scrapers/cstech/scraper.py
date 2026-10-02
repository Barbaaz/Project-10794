import logging
import time

from app.utils.utils import detetar_plataforma
from scrapers.base.base_scraper import BaseScraper
from scrapers.base.parser_utils import parse_price, detect_condition

log = logging.getLogger(__name__)


class ShopifyScraper(BaseScraper):
    """
    Shopify stores publish their whole catalogue as JSON at /products.json,
    so there is no HTML to parse. Subclasses only set store_slug and base_url.
    """

    page_size = 250  # Shopify's maximum

    def scrape_catalog(self):
        products = []

        for page in range(1, self.max_pages + 1):
            url = f"{self.base_url}/products.json"
            log.info("[%s] %s page %d", self.store_slug, url, page)

            items = self.http.get_json(url, params={"limit": self.page_size, "page": page})["products"]
            if not items:
                break

            for item in items:
                product = self.parse_item(item)
                if product:
                    products.append(product)

            time.sleep(self.delay)

        log.info("[%s] %d products", self.store_slug, len(products))
        return products

    def search(self, query):
        raise NotImplementedError(f"{self.store_slug}: only scrape_catalog() is supported")

    def is_game(self, item):
        return True

    def parse_item(self, item):
        if not self.is_game(item):
            return None

        variants = item.get("variants") or []
        if not variants:
            return None

        # Some games have one variant per region; use the cheapest one in stock
        available = [v for v in variants if v.get("available")]
        variant = min(available or variants, key=lambda v: float(v["price"]))

        price = parse_price(variant["price"])
        old_price = parse_price(variant.get("compare_at_price"))
        if old_price is not None and old_price <= price:
            old_price = None

        title = item["title"]
        images = item.get("images") or []

        # product_type ("Jogos PS5", "Jogos PC") helps when the title has no platform
        console = detetar_plataforma(title, None, item.get("product_type"))
        if not console:
            return None

        return {
            "store": self.store_slug,
            "external_name": title,
            "console": console,
            "condition": detect_condition(title, " ".join(item.get("tags") or [])),
            "price": price,
            "old_price": old_price,
            "in_stock": bool(available),
            "url": f"{self.base_url}/products/{item['handle']}",
            "image": images[0]["src"] if images else None,
        }


class CSTechScraper(ShopifyScraper):
    store_slug = "cstech"
    base_url = "https://cstech.store"

    def is_game(self, item):
        # product_type is "Jogos PS5", "Jogos Nintendo Switch 2"...; skips consoles, controllers, etc.
        return (item.get("product_type") or "").lower().startswith("jogos")
