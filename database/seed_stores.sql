-- Reference data: platforms and stores. Safe to re-run.
-- To add a store: add a row here with the same slug as its scraper's store_slug,
-- and register the scraper in scheduler/jobs.py.

USE Project10794;
GO

-- Codes match app/utils/utils.py. Older platforms (PS3, 3DS, retro...) come with the pre-owned market.
MERGE dbo.platforms AS t
USING (VALUES
    ('PS5',        N'PlayStation 5',      10),
    ('PS4',        N'PlayStation 4',      20),
    ('Switch2',    N'Nintendo Switch 2',  30),
    ('Switch',     N'Nintendo Switch',    40),
    ('XboxSeries', N'Xbox Series X|S',    50),
    ('XboxOne',    N'Xbox One',           60),
    ('PC',         N'PC',                 70),
    ('PS3',        N'PlayStation 3',      80)
) AS s (code, name, sort_order)
ON t.code = s.code
WHEN MATCHED THEN UPDATE SET name = s.name, sort_order = s.sort_order
WHEN NOT MATCHED THEN INSERT (code, name, sort_order) VALUES (s.code, s.name, s.sort_order);
GO

-- The generic 'Xbox' platform was split into XboxSeries / XboxOne. Removed once nothing uses it
-- (run python -m scheduler.run_all_scrapers and python -m pipeline.rematch first).
DELETE FROM dbo.platforms
WHERE code = 'Xbox'
  AND NOT EXISTS (SELECT 1 FROM dbo.games g WHERE g.platform_id = platforms.id)
  AND NOT EXISTS (SELECT 1 FROM dbo.store_products sp WHERE sp.platform_id = platforms.id);
GO

MERGE dbo.stores AS t
USING (VALUES
    ('press_start',   N'Press Start',   N'https://www.pressstart.pt',    1),
    ('mega-mania',    N'Mega Mania',    N'https://mega-mania.com.pt',    1),
    ('cstech',        N'CSTech',        N'https://cstech.store',         1),
    -- match-only (pipeline/matcher.py MATCH_ONLY_STORES): links to games other stores made; on since 2026-10-03
    ('radio_popular', N'Rádio Popular', N'https://www.radiopopular.pt',  1),
    ('gaming_replay', N'Gaming Replay', N'https://www.gamingreplay.com/pt/', 1)  -- since 2026-10-03
) AS s (slug, name, base_url, is_active)
ON t.slug = s.slug
-- is_active is not updated, so a store switched off in the database stays off
WHEN MATCHED AND (t.name <> s.name OR t.base_url <> s.base_url) THEN
    UPDATE SET name = s.name, base_url = s.base_url
WHEN NOT MATCHED THEN INSERT (slug, name, base_url, is_active)
    VALUES (s.slug, s.name, s.base_url, s.is_active);
GO
