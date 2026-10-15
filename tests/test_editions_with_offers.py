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
        "INSERT INTO games (platform_id, title, normalized_title) VALUES (?, 'Fav Game', 'fav game') RETURNING id",
        platform_id,
    ).fetchone()[0]
    edition_id = cursor.execute(
        "INSERT INTO game_editions (game_id, edition_key, name) VALUES (?, '', 'Standard') RETURNING id",
        game_id,
    ).fetchone()[0]

    for name, history in HISTORIES.items():
        sp_id = cursor.execute(
            "INSERT INTO store_products (store_id, game_id, edition_id, platform_id, url, external_name) "
            "SELECT id, ?, ?, ?, ?, ? FROM stores ORDER BY id LIMIT 1 RETURNING id",
            game_id, edition_id, platform_id, f"https://example.test/{name}", name,
        ).fetchone()[0]
        for price, in_stock, days_ago in history:
            cursor.execute(
                "INSERT INTO price_snapshots (store_product_id, price, in_stock, scraped_at) "
                "VALUES (?, ?, ?, utcnow() - make_interval(days => ?))",
                sp_id, price, bool(in_stock), days_ago,
            )

    yield edition_id

    cursor.execute("DELETE FROM price_snapshots ps USING store_products sp "
                   "WHERE sp.id = ps.store_product_id AND sp.edition_id = ?", edition_id)
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


def set_preorder(app_on_test_db, edition_id, days_to_release, names=None):
    """Mark these offers (all by default) as pre-orders coming out in that many days."""
    app_on_test_db.conn.cursor().execute(
        "UPDATE store_products SET is_preorder = true, release_date = (utcnow() + make_interval(days => ?))::date "
        "WHERE edition_id = ? AND (? OR external_name = ANY(?))",
        days_to_release, edition_id, names is None, names or [],
    )


def test_pre_order_when_every_offer_in_stock_is_one(app_on_test_db, edition_id):
    # the sold-out offer doesn't count: the wishlist shows "Pré-reserva" (user, 2026-10-15)
    set_preorder(app_on_test_db, edition_id, 30, ["restocked 2 days ago", "never sold out", "restocked long ago"])
    [group] = editions_with_offers([edition_id])
    assert group["is_preorder"]
    assert "own_release_date" not in group["offers"][0]


def test_not_a_pre_order_when_one_offer_in_stock_is_not(app_on_test_db, edition_id):
    set_preorder(app_on_test_db, edition_id, 30, ["restocked 2 days ago", "never sold out"])
    [group] = editions_with_offers([edition_id])
    assert not group["is_preorder"]


def test_not_a_pre_order_once_its_release_date_has_passed(app_on_test_db, edition_id):
    # some stores keep the label after the release
    set_preorder(app_on_test_db, edition_id, -3)
    [group] = editions_with_offers([edition_id])
    assert not group["is_preorder"]
    assert not any(o["is_preorder"] for o in group["offers"])


def test_unknown_editions_are_ignored(app_on_test_db):
    assert editions_with_offers([999999]) == []
    assert editions_with_offers([]) == []
