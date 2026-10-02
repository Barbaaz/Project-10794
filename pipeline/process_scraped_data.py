import logging

from core.editions import is_excluded
from db import get_connection
from pipeline.deduplicator import deduplicate
from pipeline.matcher import GameMatcher

log = logging.getLogger(__name__)

UPSERT_STORE_PRODUCT = """
MERGE store_products WITH (HOLDLOCK) AS t
USING (SELECT ? AS store_id, ? AS url, ? AS condition) AS s
    ON t.store_id = s.store_id AND t.url = s.url AND t.condition = s.condition
WHEN MATCHED THEN UPDATE SET
    game_id = ?, edition_id = ?, platform_id = ?, external_name = ?, image_url = ?,
    last_seen_at = SYSUTCDATETIME(), is_active = 1
WHEN NOT MATCHED THEN
    INSERT (store_id, url, condition, game_id, edition_id, platform_id, external_name, image_url)
    VALUES (s.store_id, s.url, s.condition, ?, ?, ?, ?, ?)
OUTPUT $action, INSERTED.id;
"""

# Only adds a row when price or stock changed since the last snapshot,
# so the table holds the price history without a copy per scrape.
# The CASTs matter: pyodbc sends None as VARCHAR(1), so ISNULL(?, -1) would become text.
INSERT_PRICE_IF_CHANGED = """
DECLARE @id INT = ?, @price DECIMAL(10,2) = ?, @old_price DECIMAL(10,2) = ?, @in_stock BIT = ?;

INSERT INTO price_snapshots (store_product_id, price, old_price, in_stock)
SELECT @id, @price, @old_price, @in_stock
WHERE NOT EXISTS (
    SELECT 1 FROM (
        SELECT TOP 1 price, old_price, in_stock
        FROM price_snapshots
        WHERE store_product_id = @id
        ORDER BY scraped_at DESC, id DESC
    ) last
    WHERE last.price = @price AND ISNULL(last.old_price, -1) = ISNULL(@old_price, -1) AND last.in_stock = @in_stock
);
"""


def process_products(store_slug, products, full_catalog=True):
    """
    Save one store's scraped products: link each to a game, upsert it in
    store_products and record its price. Everything is one transaction.

    full_catalog=True means `products` is the store's whole catalogue, so
    products not seen in this run are marked inactive (removed from the store).
    "Código na caixa" products are skipped (core.editions.is_excluded).
    """
    scraped = deduplicate(products)
    products = [p for p in scraped if not is_excluded(p["external_name"])]
    stats = {
        "products": len(products), "excluded": len(scraped) - len(products),
        "new_products": 0, "price_changes": 0, "deactivated": 0,
    }

    conn = get_connection()
    try:
        cursor = conn.cursor()

        row = cursor.execute("SELECT id FROM stores WHERE slug = ?", store_slug).fetchone()
        if not row:
            raise ValueError(f"Store '{store_slug}' is not in the stores table (see database/seed_stores.sql)")
        store_id = row[0]

        run_started_at = cursor.execute("SELECT SYSUTCDATETIME()").fetchone()[0]
        platform_ids = dict(cursor.execute("SELECT code, id FROM platforms").fetchall())
        matcher = GameMatcher(cursor, platform_ids)
        matcher.learn(p["external_name"] for p in products)

        for p in products:
            if len(p["url"]) > 800:
                log.warning("[%s] URL too long, skipped: %s", store_slug, p["url"][:100])
                continue

            game_id, edition_id = matcher.match(p)
            platform_id = platform_ids.get(p["console"])
            name = p["external_name"][:300]
            image = (p.get("image") or "")[:1000] or None

            action, store_product_id = cursor.execute(
                UPSERT_STORE_PRODUCT,
                store_id, p["url"], p["condition"],
                game_id, edition_id, platform_id, name, image,
                game_id, edition_id, platform_id, name, image,
            ).fetchone()

            if action == "INSERT":
                stats["new_products"] += 1

            cursor.execute(
                INSERT_PRICE_IF_CHANGED,
                store_product_id, p["price"], p["old_price"], p["in_stock"],
            )
            stats["price_changes"] += cursor.rowcount

        if full_catalog and products:
            cursor.execute(
                "UPDATE store_products SET is_active = 0 "
                "WHERE store_id = ? AND is_active = 1 AND last_seen_at < ?",
                store_id, run_started_at,
            )
            stats["deactivated"] = cursor.rowcount

        conn.commit()
        return stats

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
