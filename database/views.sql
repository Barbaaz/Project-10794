-- Views for the API. Run after schema.sql. Safe to re-run.

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
-- otherwise we can't know whether it was cheaper before, so is_discount = false.
--
-- Everything is worked out per product in one pass (window functions, then GROUP BY), with no
-- join of the price history to itself: such a join was planned as a loop over every product
-- (6 s for 10,000 snapshots on 2026-10-04), slowing every page that reads this view.
-- ============================================================
BEGIN;
DROP VIEW IF EXISTS current_offers;   -- re-made whole: CREATE OR REPLACE can't change its columns
CREATE VIEW current_offers AS
WITH snapshots AS (
    SELECT store_product_id, price, old_price, in_stock, scraped_at, id,
           LAG(price) OVER (PARTITION BY store_product_id ORDER BY scraped_at, id) AS previous_price,
           ROW_NUMBER() OVER (PARTITION BY store_product_id ORDER BY scraped_at DESC, id DESC) AS rn,
           MIN(scraped_at) OVER (PARTITION BY store_product_id) AS tracked_since
    FROM price_snapshots
),
-- A snapshot can be a stock-only change; keep the rows where the price changed. Each price is
-- valid from its change until the next one (valid_to NULL = current price, from price_since)
price_periods AS (
    SELECT store_product_id, price,
           LEAD(scraped_at) OVER (PARTITION BY store_product_id ORDER BY scraped_at, id) AS valid_to,
           MAX(scraped_at) OVER (PARTITION BY store_product_id) AS price_since
    FROM snapshots
    WHERE previous_price IS NULL OR previous_price <> price
),
-- Lowest price in effect during the 30 days before the current price started
per_product AS (
    SELECT store_product_id, MAX(price_since) AS price_since,
           MIN(price) FILTER (WHERE valid_to IS NOT NULL
                                AND valid_to > price_since - interval '30 days') AS reference_price
    FROM price_periods
    GROUP BY store_product_id
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
        pp.price_since,
        pp.reference_price                        -- lowest price in the 30 days before price_since
    FROM store_products sp
    JOIN snapshots l ON l.store_product_id = sp.id AND l.rn = 1
    JOIN per_product pp ON pp.store_product_id = sp.id
)
SELECT
    o.*,
    COALESCE(o.reference_price IS NOT NULL
             AND o.price < o.reference_price
             AND o.tracked_since <= o.price_since - interval '30 days', false) AS is_discount,
    CASE
        WHEN o.reference_price IS NOT NULL
         AND o.price < o.reference_price
         AND o.tracked_since <= o.price_since - interval '30 days'
        THEN CAST(ROUND(100.0 * (o.reference_price - o.price) / o.reference_price, 0) AS integer)
    END AS discount_percent
FROM offers o;
COMMIT;
