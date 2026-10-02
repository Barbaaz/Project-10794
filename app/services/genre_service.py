"""
Categories for the catalogue and search filter, from the IGDB genres stored on each game
(games.genres, "Adventure, Role-playing (RPG)"; pipeline/igdb.py). Close IGDB genres share a
category (all the strategy kinds are "strategy"). Games IGDB doesn't know have no category:
they show only when no category is chosen. Names in PT / EN are in static/i18n.js (genre_<slug>).
"""
from app.services.common import cached
from db import fetch_all

# category → the IGDB genre names it covers
GENRES = {
    "action": ["Hack and slash/Beat 'em up"],
    "adventure": ["Adventure", "Point-and-click"],
    "arcade": ["Arcade", "Pinball"],
    "card_board": ["Card & Board Game"],
    "fighting": ["Fighting"],
    "indie": ["Indie"],
    "music": ["Music"],
    "platform": ["Platform"],
    "puzzle": ["Puzzle", "Quiz/Trivia"],
    "racing": ["Racing"],
    "rpg": ["Role-playing (RPG)"],
    "shooter": ["Shooter"],
    "simulator": ["Simulator"],
    "sport": ["Sport"],
    "strategy": ["Strategy", "Turn-based strategy (TBS)", "Real Time Strategy (RTS)", "Tactical"],
    "visual_novel": ["Visual Novel"],
}


def genre_filter(genre, games_alias="g"):
    """(condition, params) for "this game is in category `genre`", or None for an unknown one.
    Exact names inside the comma-separated list, so "Strategy" doesn't also match "Tactical"."""
    names = GENRES.get(genre)
    if not names:
        return None
    padded = f"(', ' + {games_alias}.genres + ', ')"
    return "(" + " OR ".join([f"{padded} LIKE ?"] * len(names)) + ")", [f"%, {_like(n)}, %" for n in names]


def _like(text):
    return text.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")


def categories_of(genres_text):
    """The categories of one game's IGDB genres text."""
    names = {n.strip() for n in (genres_text or "").split(",")}
    return [slug for slug, covered in GENRES.items() if names & set(covered)]


def genre_counts():
    """[{genre, count}]: how many games with an offer in stock each category has (cached)."""
    def compute():
        rows = fetch_all("""
            SELECT g.genres FROM games g
            WHERE g.genres IS NOT NULL AND EXISTS (SELECT 1 FROM current_offers o
                WHERE o.game_id = g.id AND o.is_active = 1 AND o.in_stock = 1)""")
        counts = dict.fromkeys(GENRES, 0)
        for r in rows:
            for slug in categories_of(r["genres"]):
                counts[slug] += 1
        return [{"genre": slug, "count": n} for slug, n in counts.items() if n]
    return cached("genre_counts", compute)
