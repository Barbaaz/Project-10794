"""Best prices between stores (price_service.best_store_deals), shown while there are no real discounts."""
import pytest

from app.services import price_service

# edition → {store slug: (price, in stock)}
EDITIONS = {
    "half price elsewhere": {"mega-mania": (20.00, 1), "cstech": (40.00, 1), "press_start": (45.00, 1)},
    "tiny gap":             {"mega-mania": (39.00, 1), "cstech": (40.00, 1)},
    "too good to be true":  {"mega-mania": (10.00, 1), "cstech": (100.00, 1)},   # likely a wrong match
    "cheapest sold out":    {"mega-mania": (10.00, 0), "cstech": (40.00, 1), "press_start": (41.00, 1)},
    "only one store":       {"mega-mania": (10.00, 1)},
}


@pytest.fixture
def deals(app_on_test_db):
    price_service._featured_cache.clear()
    cursor = app_on_test_db.conn.cursor()
    platform_id = cursor.execute("SELECT id FROM platforms WHERE code = 'PS5'").fetchone()[0]

    for name, offers in EDITIONS.items():
        game_id = cursor.execute(
            "INSERT INTO games (platform_id, title, normalized_title) OUTPUT INSERTED.id VALUES (?, ?, ?)",
            platform_id, name, name,
        ).fetchone()[0]
        edition_id = cursor.execute(
            "INSERT INTO game_editions (game_id, edition_key, name) OUTPUT INSERTED.id VALUES (?, '', 'Standard')",
            game_id,
        ).fetchone()[0]
        for slug, (price, in_stock) in offers.items():
            sp_id = cursor.execute(
                "INSERT INTO store_products (store_id, game_id, edition_id, platform_id, url, external_name) "
                "OUTPUT INSERTED.id SELECT id, ?, ?, ?, ?, ? FROM stores WHERE slug = ?",
                game_id, edition_id, platform_id, f"https://example.test/{slug}/{name}", name, slug,
            ).fetchone()[0]
            cursor.execute("INSERT INTO price_snapshots (store_product_id, price, in_stock) VALUES (?, ?, ?)",
                           sp_id, price, in_stock)

    yield {d["title"]: d for d in price_service.best_store_deals(limit=50)}

    cursor.execute("DELETE FROM price_snapshots")
    cursor.execute("DELETE FROM store_products")
    cursor.execute("DELETE FROM game_editions")
    cursor.execute("DELETE FROM games")
    price_service._featured_cache.clear()


def test_big_gap_between_stores_is_shown(deals):
    deal = deals["half price elsewhere"]
    assert (deal["price"], deal["store"], deal["next_price"], deal["next_store"]) == (20.0, "mega-mania", 40.0, "cstech")
    assert deal["savings_percent"] == 50


def test_small_and_implausible_gaps_are_not_shown(deals):
    assert "tiny gap" not in deals
    assert "too good to be true" not in deals
    assert "only one store" not in deals


def test_deal_lists_every_store_in_stock(deals):
    offers = deals["half price elsewhere"]["offers"]
    assert [(o["store"], o["price"]) for o in offers] == [("mega-mania", 20.0), ("cstech", 40.0), ("press_start", 45.0)]
    assert all(o["url"] for o in offers)


def test_platform_filter(deals, app_on_test_db):
    price_service._featured_cache.clear()
    assert price_service.best_store_deals(platform="PS5")
    assert price_service.best_store_deals(platform="PC") == []


def test_sold_out_offers_are_not_compared(deals):
    # without the sold-out 10 €, it's 40 € vs 41 €: not a deal
    assert "cheapest sold out" not in deals
