from scrapers.base.shopify import ShopifyScraper


class DartyScraper(ShopifyScraper):
    """
    Darty (Shopify) sells everything, so only the games collection is read (~5,600 products,
    ~23 requests). Pre-orders are the products of the "Pré-vendas Gaming" collection (no tag and
    no release date: the date comes from the other stores). Its "vendor" is the platform ("Ps5"),
    not the publisher.
    """

    store_slug = "darty"
    base_url = "https://darty.pt"
    collections = ("videojogos",)
    preorder_collection = "pre-vendas-gaming"
    vendor_is_publisher = False
    # "Jogos PS5", "Jogos Switch 2"; "Jogos de Tabuleiro" has no platform, so parse_item drops it
    game_type_prefix = "jogos"
