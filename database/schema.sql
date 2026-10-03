-- Project10794 schema (SQL Server)
-- Safe to re-run: each table is only created if it does not exist yet.
--
-- Catalogue:   platforms -> games -> game_editions
-- Stores:      stores -> store_products -> price_snapshots   (filled by scrapers)
--              stores -> scrape_runs                         (one row per scraper run)
-- Marketplace: made by Alembic (migrations/, app/models.py)

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
    image_urls     NVARCHAR(MAX)  NULL,          -- JSON list: the store's photos besides the cover
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
-- Marketplace (users, listings, photos, conversations, messages, ratings, collection, reviews):
-- made by Alembic from app/models.py (migrations/); python -m database.setup runs both
-- ============================================================

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


-- Games / editions merged into another by pipeline/rematch.py: old links (/game/<id>) and
-- wishes saved in browsers (edition ids) are sent to the one that replaced them
IF OBJECT_ID('dbo.merged_ids', 'U') IS NULL
CREATE TABLE dbo.merged_ids (
    kind      VARCHAR(10) NOT NULL CHECK (kind IN ('game', 'edition')),
    old_id    INT         NOT NULL,
    new_id    INT         NOT NULL,
    merged_at DATETIME2   NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT pk_merged_ids PRIMARY KEY (kind, old_id)
);
GO

-- IGDB trailers (pipeline/igdb.py): JSON list of {"id": YouTube id, "name": "Trailer"};
-- NULL = not looked up yet, "[]" = IGDB has none
IF COL_LENGTH('dbo.games', 'video_ids') IS NULL
    ALTER TABLE dbo.games ADD video_ids NVARCHAR(MAX) NULL;
GO

-- IGDB game modes and themes, for the tag filter (app/services/tag_service.py): "Single player,
-- Co-operative" / "Horror, Survival"; NULL = not looked up yet, "" = IGDB lists none
IF COL_LENGTH('dbo.games', 'game_modes') IS NULL
    ALTER TABLE dbo.games ADD game_modes NVARCHAR(500) NULL, themes NVARCHAR(500) NULL;
GO

-- IGDB time to beat (pipeline/igdb.py, fill_time_to_beat): seconds to finish rushing / normally /
-- 100%, and how many players gave times; ttb_checked_at set even when IGDB has none
IF COL_LENGTH('dbo.games', 'ttb_normally') IS NULL
    ALTER TABLE dbo.games ADD ttb_hastily INT NULL, ttb_normally INT NULL, ttb_completely INT NULL,
        ttb_count INT NULL, ttb_checked_at DATETIME2 NULL;
GO

-- The game's English name, shown when the page is in English: IGDB's name (pipeline/igdb.py),
-- correctable by moderators. "" = looked up, IGDB has none (the store title is shown)
IF COL_LENGTH('dbo.games', 'title_en') IS NULL
    ALTER TABLE dbo.games ADD title_en NVARCHAR(300) NULL;
GO

-- A game no store sells, created from IGDB by a user selling a copy (app/services/igdb_game_service.py):
-- who created it (users.id; no foreign key, the users table is made later by Alembic)
IF COL_LENGTH('dbo.games', 'created_by') IS NULL
    ALTER TABLE dbo.games ADD created_by INT NULL;
GO

-- The store's photos of a product besides the cover (special editions: what's in the box),
-- JSON list of URLs, read with the description
IF COL_LENGTH('dbo.store_products', 'image_urls') IS NULL
BEGIN
    ALTER TABLE dbo.store_products ADD image_urls NVARCHAR(MAX) NULL;
    -- Special editions whose page was read before photos were kept: read them again
    UPDATE sp SET details_checked_at = NULL
    FROM dbo.store_products sp
    JOIN dbo.stores s ON s.id = sp.store_id
    JOIN dbo.game_editions e ON e.id = sp.edition_id
    WHERE s.slug IN ('press_start', 'mega-mania') AND e.edition_key <> '' AND sp.details_checked_at IS NOT NULL;
END
GO
