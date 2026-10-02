"""Saving a store's scraped products (pipeline/process_scraped_data.py), on a throwaway database."""
import pytest

from pipeline.process_scraped_data import process_products, to_cents


@pytest.fixture
def cursor(app_on_test_db):
    c = app_on_test_db.conn.cursor()
    for table in ("merged_ids", "moderation_log", "reports", "user_ratings", "messages", "conversations", "listing_photos",
                  "user_listings", "user_favorites", "users", "price_snapshots", "store_products", "game_editions", "games"):
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
    # 50.99499…: 50.99, as SQL Server rounds it)
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


def test_descriptions_only_replace_when_the_page_was_read(cursor):
    process_products("press_start", [product(1, details_checked=True, description="Primeira.", details={"ean13": "1"})])
    process_products("press_start", [product(1, description="Ignorada.")])
    row = cursor.execute("SELECT description, details FROM store_products WHERE url = 'https://shop.test/1'").fetchone()
    assert tuple(row) == ("Primeira.", '{"ean13": "1"}')


def test_to_cents_rounds_like_sql_server():
    assert [str(to_cents(v)) for v in (1.005, 25.995, 2.675, 10.125)] == ["1.00", "26.00", "2.67", "10.13"]
    assert to_cents(None) is None
