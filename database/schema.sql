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
-- Marketplace (users selling used games)
-- ============================================================

IF OBJECT_ID('dbo.users', 'U') IS NULL
CREATE TABLE dbo.users (
    id             INT IDENTITY(1,1) PRIMARY KEY,
    email          NVARCHAR(255) NOT NULL UNIQUE,
    password_hash  NVARCHAR(255) NULL,           -- never store plain passwords; NULL = Google / Microsoft only
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

-- Games / editions merged into another by pipeline/rematch.py: old links (/game/<id>) and
-- favourites saved in browsers (edition ids) are sent to the one that replaced them
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

-- Accounts (Phase 3): log in with username or email. password_hash is NULL for an account
-- that only signs in with Google / Microsoft. Usernames are unique (case-insensitive, like
-- the database's collation); the filtered index lets older rows without one exist.
IF COL_LENGTH('dbo.users', 'username') IS NULL
    ALTER TABLE dbo.users ADD
        username      NVARCHAR(30) NULL,
        is_admin      BIT          NOT NULL DEFAULT 0,   -- moderation
        last_login_at DATETIME2    NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_users_username')
    CREATE UNIQUE INDEX ux_users_username ON dbo.users (username) WHERE username IS NOT NULL;
GO
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.users') AND name = 'password_hash' AND is_nullable = 0)
    ALTER TABLE dbo.users ALTER COLUMN password_hash NVARCHAR(255) NULL;
GO

-- Listings may also be new (still sealed)
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_user_listings_condition'
           AND definition NOT LIKE '%''new''%')
BEGIN
    ALTER TABLE dbo.user_listings DROP CONSTRAINT ck_user_listings_condition;
    ALTER TABLE dbo.user_listings ADD CONSTRAINT ck_user_listings_condition
        CHECK (condition IN ('new', 'like_new', 'good', 'fair', 'poor'));
END
GO

-- A listing's photos (at least 3), in the order the seller chose. The files are kept by
-- app/services/photo_storage.py; these are their keys there (photo and thumbnail).
IF OBJECT_ID('dbo.listing_photos', 'U') IS NULL
CREATE TABLE dbo.listing_photos (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    listing_id  INT            NOT NULL REFERENCES dbo.user_listings(id),
    position    INT            NOT NULL,
    photo_key   NVARCHAR(200)  NOT NULL,
    thumb_key   NVARCHAR(200)  NOT NULL,
    created_at  DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_listing_photos_listing')
    CREATE INDEX ix_listing_photos_listing ON dbo.listing_photos (listing_id, position);
GO

-- Marketplace conversations: one per listing and buyer. The purchase steps live here too
-- (deal_status, see app/services/chat_service.py): none → requested → accepted → sent →
-- completed, or declined / cancelled / problem. *_read_at: unread messages for each side.
IF OBJECT_ID('dbo.conversations', 'U') IS NULL
CREATE TABLE dbo.conversations (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    listing_id       INT          NOT NULL REFERENCES dbo.user_listings(id),
    buyer_id         INT          NOT NULL REFERENCES dbo.users(id),
    seller_id        INT          NOT NULL REFERENCES dbo.users(id),
    deal_status      VARCHAR(12)  NOT NULL DEFAULT 'none',
    sent_at          DATETIME2    NULL,      -- seller marked it sent / handed over
    completed_at     DATETIME2    NULL,      -- buyer confirmed (or 7 days after sent)
    buyer_read_at    DATETIME2    NULL,
    seller_read_at   DATETIME2    NULL,
    last_message_at  DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME(),
    created_at       DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_conversations_listing_buyer UNIQUE (listing_id, buyer_id),
    CONSTRAINT ck_conversations_deal CHECK (deal_status IN
        ('none', 'requested', 'accepted', 'declined', 'cancelled', 'sent', 'completed', 'problem'))
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_conversations_buyer')
    CREATE INDEX ix_conversations_buyer ON dbo.conversations (buyer_id, last_message_at);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_conversations_seller')
    CREATE INDEX ix_conversations_seller ON dbo.conversations (seller_id, last_message_at);
GO

-- The messages of a conversation. sender_id NULL = a message from the site about a purchase
-- step (event: requested, accepted, sent…), shown differently and translated by the page.
IF OBJECT_ID('dbo.messages', 'U') IS NULL
CREATE TABLE dbo.messages (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    conversation_id  INT            NOT NULL REFERENCES dbo.conversations(id),
    sender_id        INT            NULL REFERENCES dbo.users(id),
    body             NVARCHAR(2000) NULL,
    event            VARCHAR(20)    NULL,
    created_at       DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_messages_conversation')
    CREATE INDEX ix_messages_conversation ON dbo.messages (conversation_id, id);
GO
