"""
Tags for the catalogue and search filter, next to the category (app/services/genre_service.py):
- game modes and themes, from IGDB (games.game_modes / games.themes; pipeline/igdb.py)
- prices, from our own data: on sale (a real discount), at its historical low, used copies for sale
- PEGI: up to an age (3, 7, 12, 16, 18); games without a PEGI rating are left out once it's chosen
Several tags combine: a game must have all of them. Names in PT / EN in static/i18n.js (tag_<slug>).
"""
from app.services.common import LATEST_PRICE, cached
from app.services.genre_service import games_in_stock, matching, names_filter
from db import fetch_all, placeholders

MODES = {
    "single": ["Single player"],
    "multiplayer": ["Multiplayer", "Massively Multiplayer Online (MMO)", "Battle Royale"],
    "coop": ["Co-operative"],
    "split_screen": ["Split screen"],
}
# Left out: "Action" (most games), vague ones (Drama, Non-fiction, Business), and
# "4X (explore, expand, exploit, and exterminate)", whose commas break the list
THEMES = {
    "fantasy": ["Fantasy"],
    "scifi": ["Science fiction"],
    "open_world": ["Open world"],
    "horror": ["Horror"],
    "survival": ["Survival"],
    "kids": ["Kids"],
    "party": ["Party"],
    "comedy": ["Comedy"],
    "sandbox": ["Sandbox"],
    "mystery": ["Mystery"],
    "historical": ["Historical"],
    "warfare": ["Warfare"],
    "stealth": ["Stealth"],
    "romance": ["Romance"],
    "educational": ["Educational"],
}

# The editions at their historical low: a new copy in stock now costs the lowest price ever
# recorded for the edition (any store), and that store sold it for more before — a real drop to a
# new low. (Prices that never changed don't count, nor two stores simply asking different prices.)
# The same rule for the tag, the "★ Mínimo histórico" badge on cards and the game page.
AT_HISTORICAL_LOW = f"""
    SELECT sp.edition_id FROM store_products sp {LATEST_PRICE}
    WHERE sp.is_active = 1 AND sp.condition = 'new' AND last.in_stock = 1 AND sp.edition_id IS NOT NULL
      AND EXISTS (SELECT 1 FROM price_snapshots earlier WHERE earlier.store_product_id = sp.id AND earlier.price > last.price)
      AND last.price <= (SELECT MIN(hp.price) FROM store_products h JOIN price_snapshots hp ON hp.store_product_id = h.id
                         WHERE h.edition_id = sp.edition_id AND h.condition = 'new' AND hp.in_stock = 1)"""


def mark_historical_lows(groups, key="edition_id"):
    """Set `at_historical_low` on card groups / editions (dicts with the edition id in `key`), in one query."""
    ids = list({g[key] for g in groups if g.get(key)})
    lows = {r["edition_id"] for r in fetch_all(
        f"{AT_HISTORICAL_LOW} AND sp.edition_id IN ({placeholders(ids)})", *ids)} if ids else set()
    for g in groups:
        g["at_historical_low"] = g.get(key) in lows
    return groups


# Price tags: conditions on the catalogue query's aliases (game_service.catalog: ed = the edition
# with its best price, offers = store offers in stock, used = active listings)
PRICE_TAGS = {
    "on_sale": """EXISTS (SELECT 1 FROM current_offers d WHERE d.edition_id = ed.edition_id
                  AND d.is_discount = 1 AND d.is_active = 1 AND d.in_stock = 1)""",
    "historical_low": f"ed.edition_id IN ({AT_HISTORICAL_LOW})",
    "used": "ed.edition_id IN (SELECT edition_id FROM used)",
}

PEGI_AGES = (3, 7, 12, 16, 18)
GROUPS = {"mode": MODES, "theme": THEMES}


def tag_filters(tags, games_alias="g"):
    """[(condition, params)] for the known tags in `tags` (all must match); unknown ones are ignored."""
    filters = []
    for tag in dict.fromkeys(tags or []):
        if tag in MODES:
            filters.append(names_filter(f"{games_alias}.game_modes", MODES[tag]))
        elif tag in THEMES:
            filters.append(names_filter(f"{games_alias}.themes", THEMES[tag]))
        elif tag in PRICE_TAGS:
            filters.append((PRICE_TAGS[tag], []))
    return filters


def pegi_filter(max_age, games_alias="g"):
    """(condition, params): PEGI rating up to `max_age`; None when it isn't one of PEGI_AGES."""
    if max_age not in PEGI_AGES:
        return None
    ages = [a for a in PEGI_AGES if a <= max_age]
    return f"{games_alias}.pegi IN ({', '.join('?' * len(ages))})", [str(a) for a in ages]


def tag_list():
    """[{tag, group, count}] for the filter: modes and themes with games in stock (count), then the
    price tags (count None: it changes with every price update). Cached."""
    def compute():
        rows = games_in_stock(["game_modes", "themes"])
        result = []
        for group, column in (("mode", "game_modes"), ("theme", "themes")):
            counts = dict.fromkeys(GROUPS[group], 0)
            for r in rows:
                for slug in matching(GROUPS[group], r[column]):
                    counts[slug] += 1
            result += [{"tag": slug, "group": group, "count": n} for slug, n in counts.items() if n]
        return result + [{"tag": slug, "group": "price", "count": None} for slug in PRICE_TAGS]
    return cached("tag_list", compute)
