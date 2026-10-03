"""
Pieces the services share: the offer columns sent to clients, SQL fragments, how a card
is named and built, the lowest-price query, and a small cache.
"""
import re
import time

from core.normalizer import normalize_name
from db import fetch_all

# Offer columns sent to clients. The store's own crossed-out price is deliberately
# not included: "was_price" is only set when our price history confirms a real discount.
OFFER_COLUMNS = """
    o.store_product_id AS offer_id, o.game_id, o.edition_id,
    s.slug AS store, s.name AS store_name,
    o.condition, o.price, o.in_stock, o.is_preorder, o.url, o.image_url AS image, o.external_name,
    CASE WHEN o.is_discount THEN o.reference_price END AS was_price,
    o.discount_percent, o.is_discount, o.last_seen_at
"""

# TWO_STEPS: queries pick the edition / game ids first, then read current_offers with
# "IN (ids)", so the view is only worked out for those products (on SQL Server, joining it
# to a subquery took 30 s instead of 0.1 s).

# The latest price and stock of each store product `sp`, as `last`:
#   FROM store_products sp {LATEST_PRICE} WHERE last.in_stock
LATEST_PRICE = """
    CROSS JOIN LATERAL (SELECT price, in_stock FROM price_snapshots ps
                        WHERE ps.store_product_id = sp.id ORDER BY ps.scraped_at DESC, ps.id DESC LIMIT 1) last
"""

# What card_group() needs, from game_editions e JOIN games g JOIN platforms p
EDITION_CARD_COLUMNS = """
    e.id AS edition_id, e.name AS edition, e.edition_key, g.id AS game_id, g.title, g.title_en, g.cover_image_id,
    p.code AS console, p.name AS platform_name
"""

# The game's IGDB cover, double size (528 × 748) so cards stay sharp on phone screens
IGDB_COVER = "https://images.igdb.com/igdb/image/upload/t_cover_big_2x/{}.jpg"


def card_cover(row):
    """
    The card's picture when it should be the game's IGDB cover: flat box art in the card's own 3:4
    shape (the stores' photos are square, 3D box shots or small). Only for the standard edition
    (also "· PlayStation Hits"): a special edition shows its own box, from the store.
    """
    if row.get("cover_image_id") and row["edition_key"].split("|")[0] == "":
        return IGDB_COVER.format(row["cover_image_id"])
    return None

# Portuguese edition words in English, for the English page ("Edição Especial" → "Special Edition")
EDITION_WORDS_EN = [(re.compile(rf"\b{pt}\b", re.IGNORECASE), en) for pt, en in [
    ("de colecionador", "Collector's"), ("colecionador", "Collector's"), ("jogo do ano", "Game of the Year"),
    ("especial", "Special"), ("limitada", "Limited"), ("definitiva", "Definitive"), ("completa", "Complete"),
    ("ouro", "Gold"), ("europeia", "European"), ("americana", "American"),
]]
EDITION_FIRST = re.compile(r"(edição|versão)\s+(.+)", re.IGNORECASE)


def edition_en(name):
    """An edition's name in English: "Edição Especial Limitada" → "Special Limited Edition"."""
    text = name or ""
    for pattern, english in EDITION_WORDS_EN:
        text = pattern.sub(english, text)
    if m := EDITION_FIRST.fullmatch(text):
        text = f"{m.group(2)} {'Edition' if m.group(1).lower().startswith('edi') else 'Version'}"
    return text


def title_en(row):
    """The game's English name when it has one, else its title (row: title, title_en)."""
    return row.get("title_en") or row["title"]


def better_title(row):
    """
    The title for the Portuguese page: the English name when it's the same words better written
    ("ASSASSINS CREED ODYSSEY" → "Assassin's Creed Odyssey"), else the store's title (an English
    name in other words is a translation: English page only).
    """
    english = row.get("title_en")
    return english if english and normalize_name(english) == normalize_name(row["title"]) else row["title"]

CACHE_SECONDS = 600   # prices change once a day; no need to recompute on every visit
_cache = {}


def cached(key, compute, seconds=CACHE_SECONDS):
    """compute()'s result, kept for `seconds` under `key`."""
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < seconds:
        return hit[1]
    value = compute()
    _cache[key] = (time.monotonic(), value)
    return value


def clear_cache():
    _cache.clear()


def title_word_filters(q):
    """(conditions, params): every word of q must be in the game's title (games g)."""
    words = normalize_name(q or "").split()
    return ["g.normalized_title LIKE ?"] * len(words), [f"%{w}%" for w in words]


def card_name(title, edition_key, edition):
    """ "Silent Hill f" for the Standard edition, "Silent Hill f — Day One Edition" for the others."""
    return title if edition_key == "" else f"{title} — {edition}"


def card_group(row, offers, **extra):
    """
    One card of the page (an edition with its offers), from a row with edition_id, game_id,
    title, edition_key, edition, console and platform_name.
    """
    return {
        "edition_id": row["edition_id"],
        "game_id": row["game_id"],
        "name": card_name(better_title(row), row["edition_key"], row["edition"]),
        "name_en": card_name(title_en(row), row["edition_key"], edition_en(row["edition"])),
        "cover": card_cover(row),
        "console": row["console"],
        "platform_name": row["platform_name"],
        **extra,
        "offers": offers,
    }


def lowest_prices(condition, *params):
    """
    {edition_id: {price, date, store, offer_id, tracked_since}}: the lowest price ever recorded
    for each edition of the store products matching `condition` (SQL on store_products sp),
    across all stores (also products no longer sold). Only new copies, and only while in stock:
    a used copy or a sold-out price isn't a price you could have paid. The earliest date wins a tie.
    """
    rows = fetch_all(
        f"""
        SELECT edition_id, price, date, store, offer_id, tracked_since
        FROM (
            SELECT sp.edition_id, ps.price, ps.scraped_at AS date, s.slug AS store, sp.id AS offer_id,
                   ROW_NUMBER() OVER (PARTITION BY sp.edition_id ORDER BY ps.price, ps.scraped_at, ps.id) AS rn,
                   MIN(ps.scraped_at) OVER (PARTITION BY sp.edition_id) AS tracked_since
            FROM store_products sp
            JOIN price_snapshots ps ON ps.store_product_id = sp.id
            JOIN stores s ON s.id = sp.store_id
            WHERE {condition} AND sp.condition = 'new' AND ps.in_stock
        ) x
        WHERE rn = 1
        """,
        *params,
    )
    return {r.pop("edition_id"): r for r in rows}


def page_result(page, per_page, total, **items):
    """The paging fields every paged answer has, plus its items."""
    return {"page": page, "per_page": per_page, "pages": max(1, -(-total // per_page)), "total": total, **items}
