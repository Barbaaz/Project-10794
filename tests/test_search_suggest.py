"""The header's search suggestions (game_service.suggest, /api/games/suggest; user, 2026-10-20): what Enter would
find, one row per game across platforms, titles starting with the words first."""
import pytest

from app.services import common


@pytest.fixture
def client(app_on_test_db, web_client):
    common.clear_cache()
    cursor = app_on_test_db.conn.cursor()

    def product(platform, title, price, card_key=None, store="mega-mania", in_stock=True):
        platform_id = cursor.execute("SELECT id FROM platforms WHERE code = ?", platform).fetchone()[0]
        game_id = cursor.execute(
            "INSERT INTO games (platform_id, title, normalized_title, card_key) VALUES (?, ?, ?, ?) RETURNING id",
            platform_id, title, title.lower(), card_key).fetchone()[0]
        edition_id = cursor.execute("INSERT INTO game_editions (game_id, edition_key, name) VALUES (?, '', 'Standard') "
                                    "RETURNING id", game_id).fetchone()[0]
        sp_id = cursor.execute(
            "INSERT INTO store_products (store_id, game_id, edition_id, platform_id, url, external_name) "
            "SELECT id, ?, ?, ?, ?, ? FROM stores WHERE slug = ? RETURNING id",
            game_id, edition_id, platform_id, f"https://example.test/{platform}/{title}", title, store).fetchone()[0]
        cursor.execute("INSERT INTO price_snapshots (store_product_id, price, in_stock) VALUES (?, ?, ?)",
                       sp_id, price, in_stock)
        return game_id

    product("PS5", "space quest", 49.99, card_key="space quest")
    product("Switch", "space quest", 39.99, card_key="space quest")
    product("PS5", "return to space", 19.99)
    product("PS5", "spacebound", 9.99, in_stock=False)
    product("PS5", "other game", 5.99)
    yield web_client

    for table in ("price_snapshots", "store_products", "game_editions", "games"):
        cursor.execute(f"DELETE FROM {table}")
    common.clear_cache()


def test_one_row_per_game_starting_with_the_words_first(client):
    rows = client.get("/api/games/suggest?q=space").get_json()
    assert [r["name"] for r in rows] == ["space quest", "spacebound", "return to space"]
    quest = rows[0]
    assert set(quest["platforms"]) == {"PS5", "Switch"} and quest["price"] == 39.99    # the cheapest platform's
    assert rows[1]["price"] is None                                                     # none in stock


def test_every_word_and_two_letters_at_least(client):
    assert [r["name"] for r in client.get("/api/games/suggest?q=space ret").get_json()] == ["return to space"]
    assert client.get("/api/games/suggest?q=s").get_json() == []
    assert client.get("/api/games/suggest").get_json() == []
