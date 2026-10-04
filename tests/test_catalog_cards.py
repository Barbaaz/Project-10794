"""One card per game across platforms (game_service.catalog) and one deal per game (best_store_deals)."""
import pytest

from app.services import common, game_service, price_service

# (title key, platform) → {store slug: price}; every offer new and in stock
GAMES = {
    ("shared game", "PS5"):    {"mega-mania": 30.00, "cstech": 50.00},
    ("shared game", "Switch"): {"mega-mania": 25.00, "cstech": 60.00},
    ("solo game", "PS5"):      {"press_start": 45.00},
    ("big saver", "PS5"):      {"mega-mania": 100.00, "cstech": 150.00},
}


@pytest.fixture
def catalogue(app_on_test_db):
    common.clear_cache()
    c = app_on_test_db.conn.cursor()
    for (key, platform), offers in GAMES.items():
        platform_id = c.execute("SELECT id FROM platforms WHERE code = ?", platform).fetchone()[0]
        game_id = c.execute("INSERT INTO games (platform_id, title, normalized_title) VALUES (?, ?, ?) RETURNING id",
                            platform_id, key.title(), key).fetchone()[0]
        edition_id = c.execute("INSERT INTO game_editions (game_id, edition_key, name) VALUES (?, '', 'Standard') RETURNING id",
                               game_id).fetchone()[0]
        for slug, price in offers.items():
            sp_id = c.execute(
                "INSERT INTO store_products (store_id, game_id, edition_id, platform_id, url, external_name) "
                "SELECT id, ?, ?, ?, ?, ? FROM stores WHERE slug = ? RETURNING id",
                game_id, edition_id, platform_id, f"https://example.test/{slug}/{key}/{platform}", key, slug).fetchone()[0]
            c.execute("INSERT INTO price_snapshots (store_product_id, price, in_stock) VALUES (?, ?, true)", sp_id, price)
    yield
    for table in ("price_snapshots", "store_products", "game_editions", "games"):
        c.execute(f"DELETE FROM {table}")
    common.clear_cache()


def test_a_game_on_several_platforms_is_one_card(catalogue):
    page = game_service.catalog()
    assert page["total"] == 3                                    # shared (2 platforms), solo, big saver
    cards = {g["name"]: g for g in page["groups"]}
    shared = cards["Shared Game"]
    assert shared["console"] == "Switch"                         # the cheapest platform first
    assert [a["console"] for a in shared["alternatives"]] == ["PS5"]
    assert shared["alternatives"][0]["offers"][0]["price"] == 30.0
    assert cards["Solo Game"]["alternatives"] == []
    # cheapest first across cards, by the card's lowest price
    assert [g["name"] for g in game_service.catalog(sort="price_asc")["groups"]] == ["Shared Game", "Solo Game", "Big Saver"]


def test_with_a_platform_each_platform_is_its_own_card(catalogue):
    page = game_service.catalog(platform="PS5")
    assert page["total"] == 3
    assert sorted(g["name"] for g in page["groups"]) == ["Big Saver", "Shared Game", "Solo Game"]
    assert all("alternatives" not in g for g in page["groups"])


def test_one_deal_per_game_most_money_saved_first(catalogue):
    deals = price_service.best_store_deals(limit=50)
    assert [(d["title"], d["platform"], d["savings"]) for d in deals] == [
        ("Big Saver", "PS5", 50.0),          # 33%, but 50 € saved
        ("Shared Game", "Switch", 35.0),     # its PS5 gap (20 €) left out: one deal per game
    ]
