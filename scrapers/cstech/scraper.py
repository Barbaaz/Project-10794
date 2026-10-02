from scrapers.base.shopify import ShopifyScraper


class CSTechScraper(ShopifyScraper):
    store_slug = "cstech"
    base_url = "https://cstech.store"

    game_type_prefix = "jogos"     # "Jogos PS5", "Jogos Nintendo Switch 2"

    def is_preorder(self, item):
        # tags: "pre-venda", "pre-venda PS5"
        return any(t.lower().startswith("pre-venda") for t in item.get("tags") or [])
