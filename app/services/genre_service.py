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
    """(condition, params) for "this game is in category `genre`", or None for an unknown one."""
    names = GENRES.get(genre)
    return names_filter(f"{games_alias}.genres", names) if names else None


def names_filter(column, names):
    """(condition, params): the comma-separated `column` ("Adventure, Shooter") has one of `names`.
    Whole names only, so "Strategy" doesn't also match "Turn-based strategy (TBS)"."""
    padded = f"(', ' + {column} + ', ')"
    return "(" + " OR ".join([f"{padded} LIKE ?"] * len(names)) + ")", [f"%, {_like(n)}, %" for n in names]


def _like(text):
    return text.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")


def matching(groups, text):
    """The slugs of `groups` ({slug: [names]}) that one game's comma-separated text has."""
    names = {n.strip() for n in (text or "").split(",")}
    return [slug for slug, covered in groups.items() if names & set(covered)]


def categories_of(genres_text):
    """The categories of one game's IGDB genres text."""
    return matching(GENRES, genres_text)


def games_in_stock(columns):
    """These games columns for every game with an offer in stock (for counting categories / tags)."""
    return fetch_all(f"""
        SELECT {", ".join(f"g.{c}" for c in columns)} FROM games g
        WHERE EXISTS (SELECT 1 FROM current_offers o WHERE o.game_id = g.id AND o.is_active = 1 AND o.in_stock = 1)""")


def genre_counts():
    """[{genre, count}]: how many games with an offer in stock each category has (cached)."""
    def compute():
        counts = dict.fromkeys(GENRES, 0)
        for r in games_in_stock(["genres"]):
            for slug in categories_of(r["genres"]):
                counts[slug] += 1
        return [{"genre": slug, "count": n} for slug, n in counts.items() if n]
    return cached("genre_counts", compute)
