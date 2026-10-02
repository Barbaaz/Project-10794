"""Categories from IGDB genres, for the catalogue filter."""
from app.services.genre_service import GENRES, categories_of, genre_filter


def test_categories_of_a_game():
    assert categories_of("Adventure, Role-playing (RPG)") == ["adventure", "rpg"]
    assert categories_of("Turn-based strategy (TBS), Tactical") == ["strategy"]
    assert categories_of(None) == [] and categories_of("Something New") == []


def test_unknown_category_is_no_filter():
    assert genre_filter("nonsense") is None and genre_filter(None) is None


def test_filter_matches_whole_genre_names(test_db):
    c = test_db.conn.cursor()
    ps5 = c.execute("SELECT id FROM platforms WHERE code = 'PS5'").fetchone()[0]
    ids = {}
    for title, genres in [("G Strategy", "Strategy"), ("G Rts", "Indie, Real Time Strategy (RTS)"),
                          ("G Rpg", "Adventure, Role-playing (RPG)"), ("G None", None)]:
        ids[title] = c.execute("INSERT INTO games (platform_id, title, normalized_title, genres) OUTPUT INSERTED.id "
                               "VALUES (?, ?, ?, ?)", ps5, title, title.lower(), genres).fetchone()[0]
    try:
        def matching(genre):
            condition, params = genre_filter(genre)
            found = {r[0] for r in c.execute(f"SELECT id FROM games g WHERE {condition}", *params).fetchall()}
            return sorted(t for t, i in ids.items() if i in found)
        assert matching("strategy") == ["G Rts", "G Strategy"]
        assert matching("rpg") == ["G Rpg"]
        assert matching("indie") == ["G Rts"]
        assert matching("shooter") == []
    finally:
        c.execute(f"DELETE FROM games WHERE id IN ({','.join(map(str, ids.values()))})")


def test_every_category_has_a_name_in_both_languages():
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / "static" / "i18n.js").read_text(encoding="utf-8")
    for slug in GENRES:
        assert text.count(f"genre_{slug}:") == 2, slug
