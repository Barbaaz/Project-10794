import logging

from app.utils.utils import detetar_plataforma
from scrapers.base.base_scraper import BaseScraper
from scrapers.base.parser_utils import parse_price, detect_condition, html_to_text, html_images, photo_list

log = logging.getLogger(__name__)


class ShopifyScraper(BaseScraper):
    """
    Shopify stores publish their whole catalogue as JSON at /products.json (and each
    collection at /collections/<handle>/products.json), so there is no HTML to parse.
    Subclasses set store_slug and base_url, and optionally:
        collections          read only these collections (stores that sell more than games)
        preorder_collection  products in this collection are pre-orders (also read)
        vendor_is_publisher  whether Shopify's "vendor" is the game's publisher
        game_type_prefix     only products whose product_type starts with this are games
                             ("jogos" → "Jogos PS5", "Jogos Switch 2"; skips consoles, controllers...)
    """

    page_size = 250  # Shopify's maximum
    collections = ()
    preorder_collection = None
    vendor_is_publisher = True
    game_type_prefix = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.preorder_handles = set()

    def scrape_catalog(self):
        items = {}   # by handle: a product can be in more than one collection

        if self.preorder_collection:
            preorders = self.fetch_items(f"/collections/{self.preorder_collection}/products.json")
            self.preorder_handles = {i["handle"] for i in preorders}
            items.update((i["handle"], i) for i in preorders)

        for path in [f"/collections/{c}/products.json" for c in self.collections] or ["/products.json"]:
            items.update((i["handle"], i) for i in self.fetch_items(path))

        products = [p for p in map(self.parse_item, items.values()) if p]
        for p in products:
            p["kind"] = "game"
        log.info("[%s] %d products", self.store_slug, len(products))

        # The feed has the store's consoles, controllers and headsets too (core/hardware.py), so sorting them
        # costs no request: kept with read_hardware, otherwise only noted (hardware_preview) to be checked
        hardware = []
        for page_kind in ("console", "accessory"):
            hardware += self.keep_hardware(
                [p for p in (self.parse_item(i, games_only=False) for i in items.values()
                             if not self.is_game(i) and self.type_page_kind(i) == page_kind) if p], page_kind)
        if self.read_hardware:
            return hardware + products
        self.hardware_preview = hardware
        return products

    @staticmethod
    def type_page_kind(item):
        """Its product_type as the kind of page it would be on: consoles, or accessories (everything else)."""
        return "console" if "consol" in (item.get("product_type") or "").lower() else "accessory"

    def fetch_items(self, path):
        """Every product of one listing, 250 per request."""
        items = []
        for page in range(1, self.max_pages + 1):
            url = f"{self.base_url}{path}"
            log.info("[%s] %s page %d", self.store_slug, url, page)
            batch = self.http.get_json(url, params={"limit": self.page_size, "page": page})["products"]
            if not batch:
                break
            items.extend(batch)
        return items

    def search(self, query):
        raise NotImplementedError(f"{self.store_slug}: only scrape_catalog() is supported")

    def is_game(self, item):
        if not self.game_type_prefix:
            return True
        return (item.get("product_type") or "").lower().startswith(self.game_type_prefix)

    def parse_item(self, item, games_only=True):
        if games_only and not self.is_game(item):
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

        tags = item.get("tags") or []
        return {
            "store": self.store_slug,
            "external_name": title,
            "console": console,
            "condition": detect_condition(title, " ".join(tags)),
            "price": price,
            "old_price": old_price,
            "in_stock": bool(available),
            "is_preorder": self.is_preorder(item),
            "release_date": None,          # Shopify doesn't publish it; taken from other stores
            "release_date_checked": False,
            # The description comes with the catalogue, no extra request
            "description": html_to_text(item.get("body_html")),
            "details": {"Editora": item["vendor"]} if item.get("vendor") and self.vendor_is_publisher else None,
            "images": photo_list([i["src"] for i in images[1:]] + html_images(item.get("body_html"), self.base_url),
                                 exclude=[images[0]["src"]] if images else ()),
            "details_checked": True,
            "url": f"{self.base_url}/products/{item['handle']}",
            "image": images[0]["src"] if images else None,
        }

    def is_preorder(self, item):
        return item["handle"] in self.preorder_handles
