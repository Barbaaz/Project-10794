"""
The real-discount rule (current_offers in database/views.sql), on a throwaway database.
A discount is real only when the price is below the lowest price of the 30 days before it
dropped, and we watched the product for those 30 days. The store's crossed-out price is ignored.
"""
import pytest

# (product, [(price, store's crossed-out price, in stock, days ago), ...]) → (is_discount, discount %)
SCENARIOS = {
    "fake permanent discount": ([(49.99, 59.99, 1, 60)], (False, None)),
    "real discount":           ([(59.99, None, 1, 40), (39.99, 59.99, 1, 2)], (True, 33)),
    "raise then discount":     ([(39.99, None, 1, 50), (59.99, None, 1, 10), (44.99, 59.99, 1, 0)], (False, None)),
    "too new to judge":        ([(59.99, None, 1, 5), (39.99, 59.99, 1, 2)], (False, None)),
    "sale ended":              ([(59.99, None, 1, 60), (39.99, 59.99, 1, 20), (59.99, None, 1, 5)], (False, None)),
    "stock change keeps it":   ([(59.99, None, 1, 40), (39.99, 59.99, 1, 2), (39.99, 59.99, 0, 1)], (True, 33)),
}


@pytest.fixture(scope="module")
def offers(test_db):
    cursor = test_db.cursor()
    for name, (history, _) in SCENARIOS.items():
        sp_id = cursor.execute(
            "INSERT INTO store_products (store_id, url, external_name) OUTPUT INSERTED.id "
            "SELECT TOP 1 id, ?, ? FROM stores ORDER BY id",
            f"https://example.test/{name}", name,
        ).fetchone()[0]
        for price, old_price, in_stock, days_ago in history:
            cursor.execute(
                "INSERT INTO price_snapshots (store_product_id, price, old_price, in_stock, scraped_at) "
                "VALUES (?, ?, ?, ?, DATEADD(DAY, ?, SYSUTCDATETIME()))",
                sp_id, price, old_price, in_stock, -days_ago,
            )

    rows = cursor.execute("SELECT external_name, is_discount, discount_percent FROM current_offers").fetchall()
    return {r[0]: (bool(r[1]), r[2]) for r in rows}


@pytest.mark.parametrize("name", SCENARIOS)
def test_discount_rule(offers, name):
    assert offers[name] == SCENARIOS[name][1]
