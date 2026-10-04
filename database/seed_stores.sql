-- Reference data: platforms and stores. Safe to re-run.
-- To add a store: add a row here with the same slug as its scraper's store_slug,
-- and register the scraper in scheduler/jobs.py.

-- Codes match app/utils/utils.py. Older platforms (PS3, 3DS, retro...) come with the pre-owned market.
INSERT INTO platforms (code, name, sort_order) VALUES
    ('PS5',        'PlayStation 5',      10),
    ('PS4',        'PlayStation 4',      20),
    ('Switch2',    'Nintendo Switch 2',  30),
    ('Switch',     'Nintendo Switch',    40),
    ('XboxSeries', 'Xbox Series X|S',    50),
    ('XboxOne',    'Xbox One',           60),
    ('PC',         'PC',                 70),
    -- older platforms (2026-10-03): mostly used copies people sell, created from IGDB (app/services/igdb_game_service.py)
    ('PS3',        'PlayStation 3',      80),
    ('Xbox360',    'Xbox 360',           81),
    ('WiiU',       'Wii U',              82),
    ('Wii',        'Wii',                83),
    ('3DS',        'Nintendo 3DS',       84),
    ('DS',         'Nintendo DS',        85),
    ('PSVita',     'PlayStation Vita',   86),
    ('PSP',        'PlayStation Portable', 87),
    ('PS2',        'PlayStation 2',      90),
    ('PS1',        'PlayStation',        91),
    ('Xbox',       'Xbox (original)',    92),
    ('GameCube',   'Nintendo GameCube',  93),
    ('N64',        'Nintendo 64',        94),
    ('GBA',        'Game Boy Advance',   95),
    ('GBC',        'Game Boy Color',     96),
    ('GB',         'Game Boy',           97),
    ('SNES',       'Super Nintendo',     98),
    ('NES',        'NES',                99),
    ('Dreamcast',  'Sega Dreamcast',    100),
    ('Saturn',     'Sega Saturn',       101),
    ('MegaDrive',  'Sega Mega Drive',   102),
    ('MasterSystem', 'Sega Master System', 103)
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, sort_order = EXCLUDED.sort_order;

INSERT INTO stores (slug, name, base_url, is_active) VALUES
    ('press_start',   'Press Start',   'https://www.pressstart.pt',    true),
    ('mega-mania',    'Mega Mania',    'https://mega-mania.com.pt',    true),
    ('cstech',        'CSTech',        'https://cstech.store',         true),
    -- match-only (pipeline/matcher.py MATCH_ONLY_STORES): links to games other stores made; on since 2026-10-03
    ('radio_popular', 'Rádio Popular', 'https://www.radiopopular.pt',  true),
    ('gaming_replay', 'Gaming Replay', 'https://www.gamingreplay.com/pt/', true),  -- since 2026-10-03
    -- category pages + rotating product pages (scrapers/techinn); on since 2026-10-04 (first run checked)
    ('techinn',       'Techinn',       'https://www.tradeinn.com/techinn/pt', true)
-- is_active is not updated, so a store switched off in the database stays off
ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name, base_url = EXCLUDED.base_url
    WHERE stores.name <> EXCLUDED.name OR stores.base_url <> EXCLUDED.base_url;
