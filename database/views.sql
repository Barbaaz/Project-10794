-- Views for the API. Run after schema.sql. Safe to re-run.

USE Project10794;
GO

-- ============================================================
-- current_offers: one row per store product with its current price and
-- whether it is REALLY on sale.
--
-- The stores' crossed-out price (price_snapshots.old_price) is not trusted:
-- many products show one permanently. Instead, like the EU Omnibus rule,
-- a discount is real only when the current price is lower than the lowest
-- price we recorded in the 30 days before the price dropped.
--
-- We also need to have watched the product for those whole 30 days;
-- otherwise we can't know whether it was cheaper before, so is_discount = 0.
-- ============================================================
CREATE OR ALTER VIEW dbo.current_offers AS
WITH snapshots AS (
    SELECT store_product_id, price, scraped_at, id,
           LAG(price) OVER (PARTITION BY store_product_id ORDER BY scraped_at, id) AS previous_price
    FROM dbo.price_snapshots
),
-- A snapshot can be a stock-only change; keep the rows where the price changed
price_changes AS (
    SELECT store_product_id, price, scraped_at, id
    FROM snapshots
    WHERE previous_price IS NULL OR previous_price <> price
),
-- Each price is valid from its change until the next one (valid_to NULL = current price)
price_periods AS (
    SELECT store_product_id, price,
           scraped_at AS valid_from,
           LEAD(scraped_at) OVER (PARTITION BY store_product_id ORDER BY scraped_at, id) AS valid_to
    FROM price_changes
),
current_period AS (
    SELECT store_product_id, valid_from
    FROM price_periods
    WHERE valid_to IS NULL
),
-- Lowest price in effect during the 30 days before the current price started.
-- HASH JOIN: SQL Server badly underestimates these CTEs and otherwise picks a
-- nested loop that recomputes the whole price history once per product (minutes instead of ms).
reference AS (
    SELECT c.store_product_id, MIN(p.price) AS reference_price
    FROM current_period c
    INNER HASH JOIN price_periods p
      ON p.store_product_id = c.store_product_id
     AND p.valid_to IS NOT NULL
     AND p.valid_to > DATEADD(DAY, -30, c.valid_from)
    GROUP BY c.store_product_id
),
latest AS (
    SELECT store_product_id, price, old_price, in_stock,
           ROW_NUMBER() OVER (PARTITION BY store_product_id ORDER BY scraped_at DESC, id DESC) AS rn,
           MIN(scraped_at) OVER (PARTITION BY store_product_id) AS tracked_since
    FROM dbo.price_snapshots
),
offers AS (
    SELECT
        sp.id AS store_product_id,
        sp.store_id,
        sp.game_id,
        sp.edition_id,
        sp.platform_id,
        sp.condition,
        sp.external_name,
        sp.url,
        sp.image_url,
        sp.is_active,
        sp.is_preorder,
        sp.release_date,
        sp.last_seen_at,
        l.price,
        l.in_stock,
        l.old_price AS store_claimed_old_price,   -- what the store shows crossed out; for reference only
        l.tracked_since,
        cur.valid_from AS price_since,
        ref.reference_price                       -- lowest price in the 30 days before price_since
    FROM dbo.store_products sp
    JOIN latest l ON l.store_product_id = sp.id AND l.rn = 1
    JOIN current_period cur ON cur.store_product_id = sp.id
    LEFT JOIN reference ref ON ref.store_product_id = sp.id
)
SELECT
    o.*,
    CAST(CASE
        WHEN o.reference_price IS NOT NULL
         AND o.price < o.reference_price
         AND o.tracked_since <= DATEADD(DAY, -30, o.price_since)
        THEN 1 ELSE 0 END AS BIT) AS is_discount,
    CASE
        WHEN o.reference_price IS NOT NULL
         AND o.price < o.reference_price
         AND o.tracked_since <= DATEADD(DAY, -30, o.price_since)
        THEN CAST(ROUND(100.0 * (o.reference_price - o.price) / o.reference_price, 0) AS INT)
    END AS discount_percent
FROM offers o;
GO
