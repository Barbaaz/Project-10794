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

    def product(platform, title, edition, price, hypes=None, released=SOON, store="mega-mania", preorder=True, game_id=None):
        platform_id = cursor.execute("SELECT id FROM platforms WHERE code = ?", platform).fetchone()[0]
        key = "" if edition == "Standard" else edition
        if game_id is None:
            game_id = cursor.execute(
                "INSERT INTO games (platform_id, title, normalized_title, hypes) VALUES (?, ?, ?, ?) RETURNING id",
                platform_id, title, title.lower(), hypes).fetchone()[0]
            cursor.execute("INSERT INTO game_editions (game_id, edition_key, name) VALUES (?, ?, ?)", game_id, key, edition)
        edition_id = cursor.execute("SELECT id FROM game_editions WHERE game_id = ? AND edition_key = ?", game_id, key).fetchone()[0]
        sp_id = cursor.execute(
            "INSERT INTO store_products (store_id, game_id, edition_id, platform_id, url, external_name, release_date, is_preorder) "
            "SELECT id, ?, ?, ?, ?, ?, ?, ? FROM stores WHERE slug = ? RETURNING id",
            game_id, edition_id, platform_id, f"https://example.test/{store}/{platform}/{title}", title, released,
            preorder, store).fetchone()[0]
        cursor.execute("INSERT INTO price_snapshots (store_product_id, price, in_stock) VALUES (?, ?, true)", sp_id, price)
        return game_id

    product("PS5", "Big Game", "Standard", 69.99, hypes=500)
    product("Switch2", "Big Game", "Standard", 59.99, hypes=500)
    product("PC", "Big Game", "Day One Edition", 49.99, hypes=500)        # no Standard on PC
    small = product("PS5", "Small Game", "Standard", 19.99)
    # out on IGDB a year ago (a store dates its physical edition later: Silksong, 2026-10-15)
    cursor.execute("UPDATE games SET first_release_date = ? WHERE id = ?", date.today() - timedelta(days=365), small)
    product("PS5", "Old Game", "Standard", 9.99, released=date.today() - timedelta(days=3))
    product("Switch", "Old Game", "Standard", 8.99, released=date.today() - timedelta(days=3))
    product("PS5", "Ancient Game", "Standard", 5.99, released=date.today() - timedelta(days=release_service.RECENT_DAYS + 5))
    # "31/12" at one store, sold as an ordinary game at another: out already (Silent Hill: Townfall, 2026-10-14)
    placeholder = date(date.today().year, 12, 31)
    out = product("PS5", "Out Game", "Standard", 39.99, released=placeholder)
    product("PS5", "Out Game", "Standard", 34.99, released=None, store="cstech", preorder=False, game_id=out)
    # a real date to come stays, also where a store sells it without the pre-order mark
    soon = product("PS5", "Tomorrow Game", "Standard", 59.99)
    product("PS5", "Tomorrow Game", "Standard", 58.99, released=None, store="cstech", preorder=False, game_id=soon)

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
    # IGDB's first release, for the slider to leave out a game out already (it stays in the calendar)
    assert by_name["Small Game"]["igdb_release_date"] == (date.today() - timedelta(days=365)).isoformat()
    assert by_name["Big Game"]["igdb_release_date"] is None
    assert all(g["wishes"] == 0 for g in releases)
    assert "Old Game" not in by_name                        # out already
    assert "Out Game" not in by_name and "Tomorrow Game" in by_name
    assert not any(g["name"] == "Out Game" for g in release_service.preorders())
    assert release_service.game_release_date(by_name["Tomorrow Game"]["game_id"])["release_date"] == SOON.isoformat()


def test_recent_releases_only_the_last_weeks(releases):
    """The home page's "Acabados de sair" (2026-10-15): out in the last RECENT_DAYS days, newest first, a card per
    platform with `same` to fold them; not the games to come, not the ones out long ago, not "31/12" estimates."""
    recent = release_service.recent_releases()
    assert [g["name"] for g in recent] == ["Old Game", "Old Game"]
    assert {g["console"] for g in recent} == {"PS5", "Switch"} and len({g["same"] for g in recent}) == 1
    assert all(g["offers"] and g["release_date"] == (date.today() - timedelta(days=3)).isoformat() for g in recent)
    # one platform's: chosen before the newest are taken (a platform's row stays full)
    assert [g["console"] for g in release_service.recent_releases("Switch")] == ["Switch"]
    assert release_service.recent_releases("PC") == []
