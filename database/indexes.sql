-- Indexes for the API's common queries. Run after schema.sql.

USE Project10794;
GO

-- Required for filtered indexes (sqlcmd defaults this to OFF)
SET QUOTED_IDENTIFIER ON;
GO

-- Search games by name, filter by platform
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_games_platform')
    CREATE INDEX ix_games_platform ON dbo.games (platform_id) INCLUDE (title);
GO

-- All offers for a game
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_store_products_game')
    CREATE INDEX ix_store_products_game ON dbo.store_products (game_id) WHERE is_active = 1;
GO

-- All offers for one edition
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_store_products_edition')
    CREATE INDEX ix_store_products_edition ON dbo.store_products (edition_id) WHERE is_active = 1;
GO

-- Pre-orders and upcoming releases (front page)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_store_products_release')
    CREATE INDEX ix_store_products_release ON dbo.store_products (release_date)
        INCLUDE (game_id, edition_id, is_preorder) WHERE is_active = 1 AND release_date IS NOT NULL;
GO

-- Products the matcher still has to link
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_store_products_unmatched')
    CREATE INDEX ix_store_products_unmatched ON dbo.store_products (store_id) WHERE game_id IS NULL;
GO

-- Latest price per product, and price history
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_price_snapshots_product_date')
    CREATE INDEX ix_price_snapshots_product_date
        ON dbo.price_snapshots (store_product_id, scraped_at DESC)
        INCLUDE (price, old_price, in_stock);
GO

-- Recent runs per store
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_scrape_runs_store_date')
    CREATE INDEX ix_scrape_runs_store_date ON dbo.scrape_runs (store_id, started_at DESC);
GO
