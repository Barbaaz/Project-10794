"""Lançamentos (release_service.upcoming_releases): one card per game, with what the page needs to merge its
platforms, rank the most anticipated and fill the calendar."""
from datetime import date, timedelta

import pytest

from app.services import common, release_service

SOON = date.today() + timedelta(days=10)


@pytest.fixture
def releases(app_on_test_db):
    common.clear_cache()
    cursor = app_on_test_db.conn.cursor()

    def product(platform, title, edition, price, hypes=None, released=SOON):
        platform_id = cursor.execute("SELECT id FROM platforms WHERE code = ?", platform).fetchone()[0]
        game_id = cursor.execute(
            "INSERT INTO games (platform_id, title, normalized_title, hypes) VALUES (?, ?, ?, ?) RETURNING id",
            platform_id, title, title.lower(), hypes).fetchone()[0]
        key = "" if edition == "Standard" else edition
        edition_id = cursor.execute(
            "INSERT INTO game_editions (game_id, edition_key, name) VALUES (?, ?, ?) RETURNING id",
            game_id, key, edition).fetchone()[0]
        sp_id = cursor.execute(
            "INSERT INTO store_products (store_id, game_id, edition_id, platform_id, url, external_name, release_date, is_preorder) "
            "SELECT id, ?, ?, ?, ?, ?, ?, true FROM stores WHERE slug = 'mega-mania' RETURNING id",
            game_id, edition_id, platform_id, f"https://example.test/{platform}/{title}", title, released).fetchone()[0]
        cursor.execute("INSERT INTO price_snapshots (store_product_id, price, in_stock) VALUES (?, ?, true)", sp_id, price)
        return game_id

    product("PS5", "Big Game", "Standard", 69.99, hypes=500)
    product("Switch2", "Big Game", "Standard", 59.99, hypes=500)
    product("PC", "Big Game", "Day One Edition", 49.99, hypes=500)        # no Standard on PC
    product("PS5", "Small Game", "Standard", 19.99)
    product("PS5", "Old Game", "Standard", 9.99, released=date.today() - timedelta(days=3))

    yield release_service.upcoming_releases()

    for table in ("price_snapshots", "store_products", "game_editions", "games"):
        cursor.execute(f"DELETE FROM {table}")
    common.clear_cache()


def test_one_card_per_game_and_platform_merged_by_game(releases):
    """The page folds the same `same` into one card: the PC's Day One Edition joins the others."""
    big = [g for g in releases if g["name"].startswith("Big Game")]
    assert len(big) == 3 and len({g["same"] for g in big}) == 1
    assert {g["console"] for g in big} == {"PS5", "Switch2", "PC"}
    assert all(g["offers"] and g["release_date"] == SOON.isoformat() and not g["date_is_estimate"] for g in big)


def test_most_anticipated_numbers_and_only_upcoming(releases):
    by_name = {g["name"]: g for g in releases}
    assert by_name["Big Game"]["hypes"] == 500 and by_name["Small Game"]["hypes"] == 0
    assert all(g["wishes"] == 0 for g in releases)
    assert "Old Game" not in by_name                        # out already
