"""Lançamentos (release_service.upcoming_releases): one card per game, with what the page needs to merge its
platforms, rank the most anticipated and fill the calendar."""
from datetime import date, datetime, timedelta, timezone

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
    # IGDB's date for the platform (2026-10-15), only where no store gives a real one
    igdb = lambda game_id, day, exact: cursor.execute(
        "UPDATE games SET igdb_platform_release = ?, igdb_platform_release_exact = ? WHERE id = ?", day, exact, game_id)
    igdb(product("PS5", "Tba Game", "Standard", 49.99, released=placeholder), SOON + timedelta(days=20), True)
    igdb(product("PS5", "Undated Game", "Standard", 44.99, released=None), SOON + timedelta(days=30), True)
    igdb(product("PS5", "Store Dated Game", "Standard", 39.99), SOON + timedelta(days=40), True)
    igdb(product("PS5", "Port Game", "Standard", 29.99, released=placeholder), date.today() - timedelta(days=10), True)
    igdb(product("PS5", "Year Game", "Standard", 54.99, released=placeholder), date(date.today().year + 1, 12, 31), False)

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


def test_igdb_dates_only_where_the_stores_have_none(releases):
    """User, 2026-10-15: a game the stores have "por anunciar" gets IGDB's day for its platform; a store's real
    date always wins; IGDB's year doesn't replace a store's "31/12"; a past IGDB date changes nothing."""
    by_name = {g["name"]: g for g in releases}
    day = lambda name: (by_name[name]["release_date"], by_name[name]["date_is_estimate"])
    assert day("Tba Game") == ((SOON + timedelta(days=20)).isoformat(), False)
    assert day("Undated Game") == ((SOON + timedelta(days=30)).isoformat(), False)       # pre-order, no store date
    assert day("Store Dated Game") == (SOON.isoformat(), False)
    assert day("Port Game") == (date(date.today().year, 12, 31).isoformat(), True)
    assert day("Year Game") == (date(date.today().year, 12, 31).isoformat(), True)


def test_igdb_platform_release_picks_europe_and_a_day():
    from pipeline.igdb import platform_release
    row = lambda platform, day, fmt=0, region=8, status="Full Release": {
        "platform": platform, "date": int(datetime(*day, tzinfo=timezone.utc).timestamp()),
        "date_format": {"id": fmt}, "release_region": {"id": region}, "status": {"name": status}}
    rows = [row(167, (2027, 3, 1)), row(167, (2027, 2, 20), region=1), row(167, (2026, 12, 31), fmt=2, region=1),
            row(167, (2026, 11, 1), status="Early Access"), row(167, (2026, 10, 30), fmt=7), row(130, (2026, 11, 5))]
    assert platform_release(rows, 167) == ("2027-02-20", True)              # Europe's day: not a year, early access, TBD
    assert platform_release(rows, 130) == ("2026-11-05", True)              # the port's own date
    assert platform_release([row(167, (2027, 12, 31), fmt=2)], 167) == ("2027-12-31", False)
    assert platform_release(rows, 6) == (None, None)


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
