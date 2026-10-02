"""Tags for the catalogue filter: IGDB game modes / themes, PEGI, price tags."""
from pathlib import Path

from app.services.tag_service import MODES, PRICE_TAGS, THEMES, pegi_filter, tag_filters


def test_known_tags_only():
    assert [f[0] for f in tag_filters(["nonsense", None])] == []
    assert len(tag_filters(["coop", "horror", "coop", "used"])) == 3      # repeats count once
    assert tag_filters(["used"])[0] == (PRICE_TAGS["used"], [])


def test_pegi_up_to_an_age():
    assert pegi_filter(12) == ("g.pegi IN (?, ?, ?)", ["3", "7", "12"])
    assert pegi_filter(13) is None and pegi_filter(None) is None


def test_modes_and_themes_on_the_database(test_db):
    c = test_db.conn.cursor()
    ps5 = c.execute("SELECT id FROM platforms WHERE code = 'PS5'").fetchone()[0]
    ids = {}
    for title, modes, themes, pegi in [("T Coop", "Single player, Co-operative", "Horror, Survival", "18"),
                                       ("T Solo", "Single player", "Kids", "3"),
                                       ("T Mmo", "Massively Multiplayer Online (MMO)", "", None)]:
        ids[title] = c.execute("INSERT INTO games (platform_id, title, normalized_title, game_modes, themes, pegi) "
                               "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?)",
                               ps5, title, title.lower(), modes, themes, pegi).fetchone()[0]
    try:
        def matching(tags=(), pegi=None):
            chosen = tag_filters(tags) + ([pegi_filter(pegi)] if pegi else [])
            where = " AND ".join(f[0] for f in chosen)
            params = [p for f in chosen for p in f[1]]
            found = {r[0] for r in c.execute(f"SELECT id FROM games g WHERE {where}", *params).fetchall()}
            return sorted(t for t, i in ids.items() if i in found)
        assert matching(["coop"]) == ["T Coop"]
        assert matching(["multiplayer"]) == ["T Mmo"]
        assert matching(["single", "horror"]) == ["T Coop"]
        assert matching(["single"], pegi=7) == ["T Solo"]        # no PEGI rating: left out
    finally:
        c.execute(f"DELETE FROM games WHERE id IN ({','.join(map(str, ids.values()))})")


def test_every_tag_has_a_name_in_both_languages():
    text = (Path(__file__).resolve().parent.parent / "static" / "i18n.js").read_text(encoding="utf-8")
    for slug in [*MODES, *THEMES, *PRICE_TAGS]:
        assert text.count(f"tag_{slug}:") == 2, slug


def test_catalog_with_tags(web_client):
    """Every tag runs on the real catalogue query (price tags use its aliases)."""
    for tags in ["on_sale", "historical_low", "used", "coop,horror"]:
        response = web_client.get("/api/games/catalog", query_string={"tags": tags, "pegi": 16, "genre": "rpg"})
        assert response.status_code == 200, tags
    assert web_client.get("/api/games/catalog?pegi=x").status_code == 400
