"""Saving a store's scraped products (pipeline/process_scraped_data.py), on a throwaway database."""
import pytest

from pipeline.process_scraped_data import process_products, to_cents


@pytest.fixture
def cursor(app_on_test_db):
    c = app_on_test_db.conn.cursor()
    for table in ("merged_ids", "game_reviews", "collection_items", "match_overrides", "moderation_log", "reports", "user_ratings", "messages", "conversations", "listing_photos",
                  "user_listings", "users", "price_snapshots", "store_products", "game_editions", "games"):
        c.execute(f"DELETE FROM {table}")
    return c


def product(n, price=49.99, **extra):
    return {"external_name": f"Test Game {n} PS5", "url": f"https://shop.test/{n}", "condition": "new", "console": "PS5",
            "image": None, "price": price, "old_price": None, "in_stock": True, **extra}


def snapshots(cursor, url):
    return [tuple(r) for r in cursor.execute(
        "SELECT ps.price, ps.in_stock FROM price_snapshots ps JOIN store_products sp ON sp.id = ps.store_product_id "
        "WHERE sp.url = ? ORDER BY ps.id", url).fetchall()]


def test_prices_are_recorded_only_when_they_change(cursor):
    stats = process_products("press_start", [product(1, release_date="2026-12-01", release_date_checked=True), product(2)])
    assert (stats["new_products"], stats["price_changes"]) == (2, 2)

    # same price: nothing new; a new price and out of stock: one snapshot (50.995 as a float is
    # 50.99499…: 50.99, as to_cents rounds it)
    stats = process_products("press_start", [product(1), product(2, price=50.995, in_stock=False)])
    assert (stats["new_products"], stats["price_changes"], stats["deactivated"]) == (0, 1, 0)
    assert snapshots(cursor, "https://shop.test/2") == [(to_cents(49.99), True), (to_cents(50.99), False)]

    # a release date this run didn't read is kept
    assert str(cursor.execute("SELECT release_date FROM store_products WHERE url = 'https://shop.test/1'").fetchone()[0]) \
        == "2026-12-01"
    # the same URL in other letters is the same product
    assert process_products("press_start", [product(1, url="HTTPS://SHOP.TEST/1"), product(2, price=50.995, in_stock=False)]
                            )["new_products"] == 0


def test_products_missing_from_a_full_catalogue_are_deactivated(cursor):
    process_products("press_start", [product(1), product(2)])
    assert process_products("press_start", [product(1)], full_catalog=False)["deactivated"] == 0
    assert process_products("press_start", [product(1)])["deactivated"] == 1
    assert cursor.execute("SELECT is_active FROM store_products WHERE url = 'https://shop.test/2'").fetchone()[0] is False
    # back in the catalogue: active again
    process_products("press_start", [product(1), product(2)])
    assert cursor.execute("SELECT is_active FROM store_products WHERE url = 'https://shop.test/2'").fetchone()[0] is True


def test_a_store_read_in_part_deactivates_only_what_it_no_longer_lists(cursor):
    """Techinn reads some product pages per run: one not read this run stays, one gone from its sitemap goes."""
    process_products("techinn", [product(1), product(2), product(3)])
    stats = process_products("techinn", [product(1)], still_listed={"https://shop.test/1", "https://shop.test/2"})
    assert stats["deactivated"] == 1
    active = dict(cursor.execute("SELECT url, is_active FROM store_products ORDER BY url").fetchall())
    assert active == {"https://shop.test/1": True, "https://shop.test/2": True, "https://shop.test/3": False}


def test_descriptions_only_replace_when_the_page_was_read(cursor):
    process_products("press_start", [product(1, details_checked=True, description="Primeira.", details={"ean13": "1"})])
    process_products("press_start", [product(1, description="Ignorada.")])
    row = cursor.execute("SELECT description, details FROM store_products WHERE url = 'https://shop.test/1'").fetchone()
    assert tuple(row) == ("Primeira.", '{"ean13": "1"}')


def test_a_match_only_store_links_to_known_games_and_editions_only(cursor):
    """Rádio Popular's names are cut down ("LUIGI MANS 3"): they never start a game or edition."""
    from pipeline.rematch import rematch_all

    process_products("press_start", [product(1, external_name="Test Game 1")])
    games = lambda: [tuple(r) for r in cursor.execute("SELECT title FROM games").fetchall()]
    links = lambda: {r.url[-1]: r.game_id is not None for r in cursor.execute(
        "SELECT url, game_id FROM store_products WHERE store_id = (SELECT id FROM stores WHERE slug = 'radio_popular')")}

    process_products("radio_popular", [
        product("a", external_name="TEST GAME 1"),                     # known game, Standard edition
        product("b", external_name="TEST GAME 1 COLLECTORS EDITION"),  # known game, unknown edition
        product("c", external_name="TEST GAM NINE"),                   # unknown game
    ])
    assert links() == {"a": True, "b": False, "c": False}
    assert games() == [("Test Game 1",)] and cursor.execute("SELECT COUNT(*) FROM game_editions").fetchone()[0] == 1
    # a rematch keeps to the same rule
    rematch_all()
    assert links() == {"a": True, "b": False, "c": False} and games() == [("Test Game 1",)]


def test_consoles_are_grouped_strictly_and_kept_apart_from_games(cursor):
    """Consoles (core/hardware.py): their own kind, one Standard edition, the same console across stores
    only with the same cleaned name; the catalogue lists them on their own tab."""
    from app.services.game_service import catalog
    from pipeline.rematch import rematch_all

    process_products("press_start", [
        product(1, external_name="Test Game 1 PS5"),
        product(2, external_name="Consola PS5 Slim Digital 1TB", kind="console", price=449.99),
    ])
    process_products("mega-mania", [
        product("a", external_name="PlayStation 5 Slim Digital Edition 1 TB Consola", kind="console", price=459.99),
        product("b", external_name="Consola PS5 Pro", kind="console", price=799.99),          # another model
    ])
    games = [tuple(r) for r in cursor.execute(
        "SELECT g.kind, g.normalized_title, COUNT(DISTINCT e.id) AS editions, COUNT(sp.id) AS offers FROM games g "
        "JOIN game_editions e ON e.game_id = g.id JOIN store_products sp ON sp.game_id = g.id "
        "GROUP BY g.kind, g.normalized_title ORDER BY g.kind, g.normalized_title").fetchall()]
    assert games == [("console", "console:1 digital slim tb", 1, 2), ("console", "console:pro", 1, 1),
                     ("game", "test game 1", 1, 1)]
    assert cursor.execute("SELECT DISTINCT kind FROM store_products WHERE url LIKE '%/2'").fetchone()[0] == "console"

    names = lambda **kw: sorted(g["name"] for g in catalog(**kw)["groups"])
    assert names() == ["Test Game 1"]
    assert names(kind="hardware") == names(kind="console") == ["Consola PS5 Pro", "Consola PS5 Slim Digital 1TB"]
    # the rematch links them the same way
    assert rematch_all()[0] == 0


def test_to_cents_rounds_like_sql_server():
    assert [str(to_cents(v)) for v in (1.005, 25.995, 2.675, 10.125)] == ["1.00", "26.00", "2.67", "10.13"]
    assert to_cents(None) is None
