-- Project10794 schema (SQL Server)
-- Safe to re-run: each table is only created if it does not exist yet.
--
-- Catalogue:   platforms -> games -> game_editions
-- Stores:      stores -> store_products -> price_snapshots   (filled by scrapers)
--              stores -> scrape_runs                         (one row per scraper run)
-- Marketplace: users -> user_listings -> games              (used games sold by users)

USE Project10794;
GO

-- Required to alter tables that have filtered indexes (sqlcmd defaults this to OFF)
SET QUOTED_IDENTIFIER ON;
GO

-- ============================================================
-- Catalogue
-- ============================================================

IF OBJECT_ID('dbo.platforms', 'U') IS NULL
CREATE TABLE dbo.platforms (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    code        VARCHAR(20)  NOT NULL UNIQUE,   -- 'PS5', 'Switch2', 'XboxSeries'... (matches app/utils/utils.py)
    name        NVARCHAR(100) NOT NULL,
    sort_order  INT          NOT NULL DEFAULT 100 -- display order in lists and filters
);
GO

-- One row per game per platform, shared by every store and by user listings.
-- Editions (Deluxe, Day One...) are in game_editions, not separate games.
IF OBJECT_ID('dbo.games', 'U') IS NULL
CREATE TABLE dbo.games (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    platform_id      INT           NOT NULL REFERENCES dbo.platforms(id),
    title            NVARCHAR(300) NOT NULL,     -- display name, without edition: "Silent Hill: Townfall"
    normalized_title NVARCHAR(300) NOT NULL,     -- ParsedTitle.game_key (core/editions.py), used for matching
    image_url        NVARCHAR(1000) NULL,
    created_at       DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_games_title_platform UNIQUE (normalized_title, platform_id)
);
GO

-- Editions of a game: Standard, Deluxe, Day One, Collector's, Game Key Card...
IF OBJECT_ID('dbo.game_editions', 'U') IS NULL
CREATE TABLE dbo.game_editions (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    game_id      INT           NOT NULL REFERENCES dbo.games(id),
    edition_key  NVARCHAR(200) NOT NULL,         -- ParsedTitle.edition_key: "" = standard, "deluxe", "|Game Key Card"
    name         NVARCHAR(200) NOT NULL,         -- display name: "Standard", "Deluxe Edition"
    created_at   DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_game_editions UNIQUE (game_id, edition_key)
);
GO

-- ============================================================
-- Stores and scraped data
-- ============================================================

IF OBJECT_ID('dbo.stores', 'U') IS NULL
CREATE TABLE dbo.stores (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    slug        VARCHAR(50)   NOT NULL UNIQUE,  -- matches the "store" value the scrapers emit
    name        NVARCHAR(100) NOT NULL,
    base_url    NVARCHAR(500) NOT NULL,
    is_active   BIT           NOT NULL DEFAULT 1, -- turn a scraper off without deleting its history
    created_at  DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

-- One row per listing on a store's website. Updated in place on every scrape.
IF OBJECT_ID('dbo.store_products', 'U') IS NULL
CREATE TABLE dbo.store_products (
    id             INT IDENTITY(1,1) PRIMARY KEY,
    store_id       INT            NOT NULL REFERENCES dbo.stores(id),
    game_id        INT            NULL REFERENCES dbo.games(id), -- NULL until the matcher links it
    edition_id     INT            NULL REFERENCES dbo.game_editions(id),
    platform_id    INT            NULL REFERENCES dbo.platforms(id),
    external_name  NVARCHAR(300)  NOT NULL,      -- name exactly as the store shows it
    url            NVARCHAR(800)  NOT NULL,      -- 800 keeps (store_id, url, condition) under SQL Server's 1700-byte key limit
    image_url      NVARCHAR(1000) NULL,
    condition      VARCHAR(10)    NOT NULL DEFAULT 'new',
    is_preorder    BIT            NOT NULL DEFAULT 0,
    release_date   DATE           NULL,          -- as the store announces it; 31/12 often means "this year, no date yet"
    release_date_checked_at DATETIME2 NULL,      -- last time the date was read from the product page (Press Start)
    description    NVARCHAR(MAX)  NULL,          -- the store's product description, as plain text
    details        NVARCHAR(MAX)  NULL,          -- JSON {"Editora": "...", "Género": "..."} from the store's data sheet
    details_checked_at DATETIME2  NULL,          -- when the product page was read (read once)
    first_seen_at  DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
    last_seen_at   DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
    is_active      BIT            NOT NULL DEFAULT 1, -- 0 when it disappears from the store
    -- condition is part of the key: a store can sell new and used copies on the same page
    CONSTRAINT uq_store_products_url UNIQUE (store_id, url, condition),
    CONSTRAINT ck_store_products_condition CHECK (condition IN ('new', 'used'))
);
GO

-- Price history: a new row only when price, old price or stock changes.
-- store_products.last_seen_at says when the latest price was last confirmed.
IF OBJECT_ID('dbo.price_snapshots', 'U') IS NULL
CREATE TABLE dbo.price_snapshots (
    id                BIGINT IDENTITY(1,1) PRIMARY KEY,
    store_product_id  INT           NOT NULL REFERENCES dbo.store_products(id),
    price             DECIMAL(10,2) NOT NULL,     -- price the customer pays now
    old_price         DECIMAL(10,2) NULL,         -- crossed-out price when on sale
    in_stock          BIT           NOT NULL,
    scraped_at        DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

-- Lets you see when a store's scraper breaks (e.g. the site changed its HTML).
IF OBJECT_ID('dbo.scrape_runs', 'U') IS NULL
CREATE TABLE dbo.scrape_runs (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    store_id        INT            NOT NULL REFERENCES dbo.stores(id),
    started_at      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
    finished_at     DATETIME2      NULL,
    status          VARCHAR(10)    NOT NULL DEFAULT 'running',
    products_found  INT            NULL,
    error_message   NVARCHAR(MAX)  NULL,
    -- warning: far fewer products than last time, missing products were not deactivated
    CONSTRAINT ck_scrape_runs_status CHECK (status IN ('running', 'success', 'warning', 'failed'))
);
GO

-- ============================================================
-- Marketplace (users selling used games)
-- ============================================================

IF OBJECT_ID('dbo.users', 'U') IS NULL
CREATE TABLE dbo.users (
    id             INT IDENTITY(1,1) PRIMARY KEY,
    email          NVARCHAR(255) NOT NULL UNIQUE,
    password_hash  NVARCHAR(255) NOT NULL,       -- never store plain passwords
    display_name   NVARCHAR(100) NOT NULL,
    location       NVARCHAR(100) NULL,           -- e.g. city, for local pickup
    is_active      BIT           NOT NULL DEFAULT 1,
    created_at     DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

-- A user's game for sale. Linked to games so it shows next to store prices.
IF OBJECT_ID('dbo.user_listings', 'U') IS NULL
CREATE TABLE dbo.user_listings (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    user_id      INT            NOT NULL REFERENCES dbo.users(id),
    game_id      INT            NOT NULL REFERENCES dbo.games(id),
    edition_id   INT            NULL REFERENCES dbo.game_editions(id), -- NULL = seller didn't say
    price        DECIMAL(10,2)  NOT NULL,
    condition    VARCHAR(10)    NOT NULL,
    description  NVARCHAR(2000) NULL,
    status       VARCHAR(10)    NOT NULL DEFAULT 'active',
    created_at   DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at   DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
    sold_at      DATETIME2      NULL,
    CONSTRAINT ck_user_listings_condition CHECK (condition IN ('like_new', 'good', 'fair', 'poor')),
    CONSTRAINT ck_user_listings_status    CHECK (status IN ('active', 'reserved', 'sold', 'removed')),
    CONSTRAINT ck_user_listings_price     CHECK (price > 0)
);
GO

-- ============================================================
-- Upgrades for databases created before a column existed
-- ============================================================

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE name = 'ck_scrape_runs_status' AND definition LIKE '%warning%')
BEGIN
    ALTER TABLE dbo.scrape_runs DROP CONSTRAINT ck_scrape_runs_status;
    ALTER TABLE dbo.scrape_runs ADD CONSTRAINT ck_scrape_runs_status
        CHECK (status IN ('running', 'success', 'warning', 'failed'));
END
GO

IF COL_LENGTH('dbo.store_products', 'is_preorder') IS NULL
    ALTER TABLE dbo.store_products ADD
        is_preorder BIT NOT NULL DEFAULT 0,
        release_date DATE NULL,
        release_date_checked_at DATETIME2 NULL;
GO

-- Game information from IGDB (pipeline/igdb.py); igdb_checked_at is set even when no match was found
IF COL_LENGTH('dbo.games', 'igdb_id') IS NULL
    ALTER TABLE dbo.games ADD
        igdb_id INT NULL,
        igdb_checked_at DATETIME2 NULL,
        summary NVARCHAR(MAX) NULL,          -- in English
        genres NVARCHAR(500) NULL,           -- "Adventure, Shooter"
        publishers NVARCHAR(500) NULL,
        developers NVARCHAR(500) NULL,
        first_release_date DATE NULL,
        rating INT NULL,                     -- IGDB total rating 0-100
        pegi NVARCHAR(10) NULL,              -- "16"
        cover_image_id NVARCHAR(50) NULL,
        screenshot_ids NVARCHAR(MAX) NULL;   -- JSON list of IGDB image ids
GO

IF COL_LENGTH('dbo.store_products', 'description') IS NULL
    ALTER TABLE dbo.store_products ADD
        description NVARCHAR(MAX) NULL,
        details NVARCHAR(MAX) NULL,
        details_checked_at DATETIME2 NULL;
GO

IF COL_LENGTH('dbo.platforms', 'sort_order') IS NULL
    ALTER TABLE dbo.platforms ADD sort_order INT NOT NULL DEFAULT 100;
GO

IF COL_LENGTH('dbo.store_products', 'edition_id') IS NULL
    ALTER TABLE dbo.store_products ADD edition_id INT NULL REFERENCES dbo.game_editions(id);
GO

IF COL_LENGTH('dbo.user_listings', 'edition_id') IS NULL
    ALTER TABLE dbo.user_listings ADD edition_id INT NULL REFERENCES dbo.game_editions(id);
GO
