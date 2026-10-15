-- Indexes for the API's common queries. Run after schema.sql. Safe to re-run.

-- Search games by name, filter by platform
CREATE INDEX IF NOT EXISTS ix_games_platform ON games (platform_id) INCLUDE (title);

-- All offers for a game
CREATE INDEX IF NOT EXISTS ix_store_products_game ON store_products (game_id) WHERE is_active;

-- All offers for one edition
CREATE INDEX IF NOT EXISTS ix_store_products_edition ON store_products (edition_id) WHERE is_active;

-- An edition's products also no longer sold: its lowest price ever (tag_service.AT_HISTORICAL_LOW) counts them.
-- Without it that check read the whole table once per product (6 s for the catalogue's lows, 2026-10-15)
CREATE INDEX IF NOT EXISTS ix_store_products_edition_all ON store_products (edition_id, condition);

-- Pre-orders and upcoming releases (front page)
CREATE INDEX IF NOT EXISTS ix_store_products_release ON store_products (release_date)
    INCLUDE (game_id, edition_id, is_preorder) WHERE is_active AND release_date IS NOT NULL;

-- Products the matcher still has to link
CREATE INDEX IF NOT EXISTS ix_store_products_unmatched ON store_products (store_id) WHERE game_id IS NULL;

-- Latest price per product, and price history
CREATE INDEX IF NOT EXISTS ix_price_snapshots_product_date
    ON price_snapshots (store_product_id, scraped_at DESC)
    INCLUDE (price, old_price, in_stock);

-- Recent runs per store
CREATE INDEX IF NOT EXISTS ix_scrape_runs_store_date ON scrape_runs (store_id, started_at DESC);
