"""
The wishlist tab's endpoint (game_service.editions_with_offers): offers per edition,
the historical low, and back-in-stock detection from the price history.
"""
import pytest

from app.services.game_service import editions_with_offers

# store product → [(price, in stock, days ago), ...]
HISTORIES = {
    "restocked 2 days ago":  [(59.99, 1, 20), (59.99, 0, 10), (54.99, 1, 2)],
    "never sold out":        [(49.99, 1, 20)],
    "restocked long ago":    [(44.99, 1, 40), (44.99, 0, 35), (44.99, 1, 30)],
    "sold out again":        [(39.99, 1, 20), (39.99, 0, 10), (39.99, 1, 5), (39.99, 0, 1)],
}


@pytest.fixture
def edition_id(app_on_test_db):
    cursor = app_on_test_db.conn.cursor()
    platform_id = cursor.execute("SELECT id FROM platforms WHERE code = 'PS5'").fetchone()[0]
    game_id = cursor.execute(
        "INSERT INTO games (platform_id, title, normalized_title) OUTPUT INSERTED.id VALUES (?, 'Fav Game', 'fav game')",
        platform_id,
    ).fetchone()[0]
    edition_id = cursor.execute(
        "INSERT INTO game_editions (game_id, edition_key, name) OUTPUT INSERTED.id VALUES (?, '', 'Standard')",
        game_id,
    ).fetchone()[0]

    for name, history in HISTORIES.items():
        sp_id = cursor.execute(
            "INSERT INTO store_products (store_id, game_id, edition_id, platform_id, url, external_name) "
            "OUTPUT INSERTED.id SELECT TOP 1 id, ?, ?, ?, ?, ? FROM stores ORDER BY id",
            game_id, edition_id, platform_id, f"https://example.test/{name}", name,
        ).fetchone()[0]
        for price, in_stock, days_ago in history:
            cursor.execute(
                "INSERT INTO price_snapshots (store_product_id, price, in_stock, scraped_at) "
                "VALUES (?, ?, ?, DATEADD(DAY, ?, SYSUTCDATETIME()))",
                sp_id, price, in_stock, -days_ago,
            )

    yield edition_id

    cursor.execute("DELETE ps FROM price_snapshots ps JOIN store_products sp ON sp.id = ps.store_product_id "
                   "WHERE sp.edition_id = ?", edition_id)
    cursor.execute("DELETE FROM store_products WHERE edition_id = ?", edition_id)
    cursor.execute("DELETE FROM game_editions WHERE id = ?", edition_id)
    cursor.execute("DELETE FROM games WHERE id = ?", game_id)


def test_edition_with_offers(edition_id):
    [group] = editions_with_offers([edition_id])
    assert group["name"] == "Fav Game"
    assert group["console"] == "PS5"
    assert len(group["offers"]) == 4
    # in stock first, cheapest first
    assert [o["in_stock"] for o in group["offers"]] == [True, True, True, False]


def test_back_in_stock_only_recent_and_still_in_stock(edition_id):
    [group] = editions_with_offers([edition_id])
    restocked = {o["external_name"] for o in group["offers"] if o["restocked_at"]}
    assert restocked == {"restocked 2 days ago"}


def test_historical_low_counts_only_in_stock_prices(edition_id):
    [group] = editions_with_offers([edition_id])
    # 39.99 was in stock 20 days ago ("sold out again")
    assert group["lowest_price"]["price"] == 39.99


def test_unknown_editions_are_ignored(app_on_test_db):
    assert editions_with_offers([999999]) == []
    assert editions_with_offers([]) == []
