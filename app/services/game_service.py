import json
import re

from app.services.common import (
    EDITION_CARD_COLUMNS, LATEST_PRICE, OFFER_COLUMNS, card_group, lowest_prices, page_result, title_word_filters,
)
from app.services.genre_service import genre_filter
from app.services.listing_service import used_summaries
from app.services.tag_service import pegi_filter, tag_filters
from app.services.release_service import game_release_date, game_release_dates
from db import fetch_all, fetch_one, placeholders

# A special edition whose game is a download code, not a disc ("Jogo Completo (Download Digital)")
DIGITAL_CODE = re.compile(r"download\s+digital|digital\s+download|c[oó]digo\s+(de\s+)?(download|digital|descarga)",
                          re.IGNORECASE)

# A favourite that came back in stock is flagged for this many days
RESTOCK_ALERT_DAYS = 14

def search_filters(q, platform):
    """WHERE clause + params: every word of q must appear in the game's title."""
    words, params = title_word_filters(q)
    where = ["EXISTS (SELECT 1 FROM store_products sp WHERE sp.game_id = g.id AND sp.is_active = 1)", *words]

    if platform:
        where.append("p.code = ?")
        params.append(platform)

    return " AND ".join(where), params


def list_games(q=None, platform=None, page=1, per_page=20):
    where, params = search_filters(q, platform)

    total = fetch_one(
        f"SELECT COUNT(*) AS total FROM games g JOIN platforms p ON p.id = g.platform_id WHERE {where}",
        *params,
    )["total"]

    games = fetch_all(
        f"""
        SELECT g.id, g.title, p.code AS platform, g.image_url AS image
        FROM games g JOIN platforms p ON p.id = g.platform_id
        WHERE {where}
        ORDER BY g.title, p.code
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """,
        *params, (page - 1) * per_page, per_page,
    )

    summaries = offer_summaries([g["id"] for g in games])
    for game in games:
        game.update(summaries.get(game["id"], {}))

    return page_result(page, per_page, total, games=games)


def offer_summaries(game_ids):
    """{game_id: best price in stock, number of stores / editions, any real discount}"""
    if not game_ids:
        return {}

    rows = fetch_all(
        f"""
        SELECT game_id,
               MIN(CASE WHEN in_stock = 1 THEN price END) AS best_price,
               COUNT(DISTINCT store_id) AS stores,
               COUNT(DISTINCT edition_id) AS editions,
               CAST(MAX(CAST(is_discount AS INT)) AS BIT) AS has_discount
        FROM current_offers
        WHERE is_active = 1 AND game_id IN ({placeholders(game_ids)})
        GROUP BY game_id
        """,
        *game_ids,
    )
    return {r.pop("game_id"): r for r in rows}


def get_game(game_id):
    """A game with its editions, each with its store offers (cheapest in-stock first)."""
    game = fetch_one(
        """
        SELECT g.id, g.title, p.code AS platform, p.name AS platform_name, g.image_url AS image,
               g.igdb_id, g.summary, g.genres, g.publishers, g.developers, g.first_release_date,
               g.rating, g.pegi, g.cover_image_id, g.screenshot_ids, g.video_ids AS videos
        FROM games g JOIN platforms p ON p.id = g.platform_id
        WHERE g.id = ?
        """,
        game_id,
    )
    if not game:
        return None
    game["screenshot_ids"] = json.loads(game["screenshot_ids"]) if game["screenshot_ids"] else []
    game["videos"] = json.loads(game["videos"]) if game["videos"] else []

    editions = fetch_all(
        "SELECT id, name FROM game_editions WHERE game_id = ? ORDER BY CASE WHEN edition_key = '' THEN 0 ELSE 1 END, name",
        game_id,
    )
    offers = fetch_all(
        f"""
        SELECT {OFFER_COLUMNS}
        FROM current_offers o JOIN stores s ON s.id = o.store_id
        WHERE o.game_id = ? AND o.is_active = 1
        ORDER BY o.in_stock DESC, o.price
        """,
        game_id,
    )

    lowest = lowest_prices("sp.game_id = ?", game_id)
    descriptions = store_descriptions(game_id)
    photos = store_photos(game_id)

    for edition in editions:
        edition["offers"] = [o for o in offers if o["edition_id"] == edition["id"]]
        in_stock = [o["price"] for o in edition["offers"] if o["in_stock"]]
        edition["best_price"] = min(in_stock) if in_stock else None
        edition["lowest_price"] = lowest.get(edition["id"])
        # What the stores say about this edition (special editions: what's in the box)
        edition["descriptions"] = [d for d in descriptions if d["edition_id"] == edition["id"]]
        edition["digital_code"] = any(DIGITAL_CODE.search(d["text"]) for d in edition["descriptions"])
        # The stores' photos besides the cover (special editions: what's in the box)
        edition["photos"] = photos.get(edition["id"], [])

    # Store details (publisher, genre...) merged across stores, first value wins
    game["store_details"] = {}
    for d in descriptions:
        for key, value in (d["details"] or {}).items():
            game["store_details"].setdefault(key, value)

    # Editions whose products all left the stores have nothing to show
    game["editions"] = [e for e in editions if e["offers"]]

    release = game_release_date(game_id) or {}
    game["release_date"] = release.get("release_date")
    game["date_is_estimate"] = release.get("date_is_estimate", False)
    return game


def store_descriptions(game_id):
    """The stores' product descriptions for a game, longest first, one per store and edition."""
    rows = fetch_all(
        """
        SELECT sp.edition_id, s.slug AS store, s.name AS store_name, sp.description AS text, sp.details
        FROM store_products sp JOIN stores s ON s.id = sp.store_id
        WHERE sp.game_id = ? AND sp.is_active = 1 AND sp.description IS NOT NULL AND LEN(sp.description) > 20
        ORDER BY LEN(sp.description) DESC
        """,
        game_id,
    )
    seen, result = set(), []
    for r in rows:
        if (r["edition_id"], r["store"]) in seen:
            continue
        seen.add((r["edition_id"], r["store"]))
        r["details"] = json.loads(r["details"]) if r["details"] else None
        result.append(r)
    return result


def store_photos(game_id, limit=12):
    """{edition_id: [{url, store}]}: the stores' photos of each edition, no repeats, at most `limit`."""
    rows = fetch_all(
        """
        SELECT sp.edition_id, s.slug AS store, sp.image_urls
        FROM store_products sp JOIN stores s ON s.id = sp.store_id
        WHERE sp.game_id = ? AND sp.is_active = 1 AND sp.image_urls IS NOT NULL
        ORDER BY s.slug
        """,
        game_id,
    )
    result = {}
    for r in rows:
        photos = result.setdefault(r["edition_id"], [])
        for url in json.loads(r["image_urls"]):
            if len(photos) < limit and all(p["url"] != url for p in photos):
                photos.append({"url": url, "store": r["store"]})
    return result


def merged_into(kind, ids):
    """{old id: id now}: games / editions merged into another (pipeline/rematch.py, merged_ids)."""
    if not ids:
        return {}
    return dict((r["old_id"], r["new_id"]) for r in fetch_all(
        f"SELECT old_id, new_id FROM merged_ids WHERE kind = ? AND old_id IN ({placeholders(ids)})",
        kind, *ids,
    ))


def editions_with_offers(edition_ids):
    """
    For the favourites tab: each edition as a card group (same shape as /search) with all its
    current offers (in stock first, cheapest first) and its historical low (new, in stock).
    Offers that came back in stock in the last RESTOCK_ALERT_DAYS days have `restocked_at`.
    Editions no store sells anymore are kept, with no offers, so a favourite doesn't vanish.
    """
    if not edition_ids:
        return []
    ids = placeholders(edition_ids)

    editions = fetch_all(
        f"""
        SELECT {EDITION_CARD_COLUMNS}, g.image_url AS image
        FROM game_editions e
        JOIN games g ON g.id = e.game_id
        JOIN platforms p ON p.id = g.platform_id
        WHERE e.id IN ({ids})
        """,
        *edition_ids,
    )
    # Two steps on purpose (see TWO_STEPS): filter current_offers by id, not by a join
    offers = fetch_all(
        f"""
        SELECT {OFFER_COLUMNS}
        FROM current_offers o JOIN stores s ON s.id = o.store_id
        WHERE o.is_active = 1 AND o.edition_id IN ({ids})
        ORDER BY o.in_stock DESC, o.price
        """,
        *edition_ids,
    )
    lowest = lowest_prices(f"sp.edition_id IN ({ids})", *edition_ids)

    # Back in stock: the latest change from sold out to in stock, if recent. Read from the
    # price history, so it works even if the visitor wasn't here while it was sold out.
    restocked = dict((r["offer_id"], r["restocked_at"]) for r in fetch_all(
        f"""
        SELECT store_product_id AS offer_id, MAX(scraped_at) AS restocked_at
        FROM (
            SELECT ps.store_product_id, ps.scraped_at, ps.in_stock,
                   LAG(ps.in_stock) OVER (PARTITION BY ps.store_product_id ORDER BY ps.scraped_at, ps.id) AS was_in_stock
            FROM price_snapshots ps
            JOIN store_products sp ON sp.id = ps.store_product_id
            WHERE sp.edition_id IN ({ids})
        ) x
        WHERE in_stock = 1 AND was_in_stock = 0
        GROUP BY store_product_id
        HAVING MAX(scraped_at) > DATEADD(DAY, ?, SYSUTCDATETIME())
        """,
        *edition_ids, -RESTOCK_ALERT_DAYS,
    ))
    for o in offers:
        o["restocked_at"] = restocked.get(o["offer_id"]) if o["in_stock"] else None

    order = {edition_id: i for i, edition_id in enumerate(edition_ids)}
    used = used_summaries(edition_ids)
    return [
        card_group(e, [o for o in offers if o["edition_id"] == e["edition_id"]],
                   image=e["image"], lowest_price=lowest.get(e["edition_id"]), used=used.get(e["edition_id"]))
        for e in sorted(editions, key=lambda e: order[e["edition_id"]])
    ]


CATALOG_SORTS = {
    "name": "g.title, p.sort_order, CASE WHEN e.edition_key = '' THEN 0 ELSE 1 END, e.name",
    "price_asc": "ed.best_price, g.title",
    "price_desc": "ed.best_price DESC, g.title",
}


def catalog(platform=None, sort="name", page=1, per_page=48, special_only=False, q=None, store=None, genre=None,
            tags=None, pegi=None):
    """
    The whole catalogue: every edition with at least one offer in stock at a store or a used
    copy for sale by a user, as card groups (same shape as /search), one page at a time; each
    group has `used` ({count, price, listing_id}) when users sell it. sort: name / price_asc /
    price_desc (the lowest price, store or used).
    special_only: only editions above Standard (Deluxe, Collector's, Steelbook...). Keys are
    "" for Standard and "|Game Key Card" for a Standard that only differs in format.
    q: every word must be in the game's title (the search uses this).
    store: only editions this store has in stock (all stores' offers and used copies are still
    shown, to compare).
    genre: only games in this category (app/services/genre_service.py); an unknown one is ignored.
    tags: only games with all these tags; pegi: PEGI rating up to this age (app/services/tag_service.py).
    """
    order_by = CATALOG_SORTS.get(sort, CATALOG_SORTS["name"])
    in_stock_editions = f"""
        WITH offers AS (
            SELECT sp.id AS store_product_id, sp.edition_id, sp.store_id, sp.condition, last.price
            FROM store_products sp {LATEST_PRICE}
            WHERE sp.is_active = 1 AND last.in_stock = 1 AND sp.edition_id IS NOT NULL
        ),
        used AS (
            SELECT edition_id, price FROM user_listings WHERE status = 'active' AND edition_id IS NOT NULL
        ),
        ed AS (
            SELECT edition_id, MIN(price) AS best_price
            FROM (SELECT edition_id, price FROM offers UNION ALL SELECT edition_id, price FROM used) x
            GROUP BY edition_id
        )
    """
    filters, params = ["(? IS NULL OR p.code = ?)"], [platform, platform]
    if special_only:
        filters.append("e.edition_key <> '' AND e.edition_key NOT LIKE '|%'")
    words, word_params = title_word_filters(q)
    filters += words
    params += word_params
    if store:
        filters.append("ed.edition_id IN (SELECT o.edition_id FROM offers o JOIN stores s ON s.id = o.store_id "
                       "WHERE s.slug = ?)")
        params.append(store)
    for chosen in [genre_filter(genre), pegi_filter(pegi), *tag_filters(tags)]:
        if chosen:                                  # None: not chosen, or not a known one
            filters.append(chosen[0])
            params += chosen[1]
    filters = " AND ".join(filters)

    total = fetch_one(
        f"""{in_stock_editions}
        SELECT COUNT(*) AS total FROM ed
        JOIN game_editions e ON e.id = ed.edition_id
        JOIN games g ON g.id = e.game_id
        JOIN platforms p ON p.id = g.platform_id
        WHERE {filters}""",
        *params,
    )["total"]

    page_editions = fetch_all(
        f"""{in_stock_editions}
        SELECT {EDITION_CARD_COLUMNS}, g.image_url AS image
        FROM ed
        JOIN game_editions e ON e.id = ed.edition_id
        JOIN games g ON g.id = e.game_id
        JOIN platforms p ON p.id = g.platform_id
        WHERE {filters}
        ORDER BY {order_by}
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY""",
        *params, (page - 1) * per_page, per_page,
    )

    groups = []
    if page_editions:
        ids = [e["edition_id"] for e in page_editions]
        # Two steps on purpose (see TWO_STEPS): filter current_offers by id, not by a join
        offers = fetch_all(
            f"""
            SELECT {OFFER_COLUMNS}
            FROM current_offers o JOIN stores s ON s.id = o.store_id
            WHERE o.is_active = 1 AND o.in_stock = 1 AND o.edition_id IN ({placeholders(ids)})
            ORDER BY o.price
            """,
            *ids,
        )
        used = used_summaries(ids)
        groups = [card_group(e, [o for o in offers if o["edition_id"] == e["edition_id"]],
                             image=e["image"], used=used.get(e["edition_id"]))
                  for e in page_editions]

        # Games not out yet: their release date, so the card can say so
        pre_order_games = {g["game_id"] for g in groups if g["offers"] and all(o["is_preorder"] for o in g["offers"])}
        dates = game_release_dates(list(pre_order_games))
        for g in groups:
            g["is_preorder"] = g["game_id"] in pre_order_games
            release = dates.get(g["game_id"]) or {}
            g["release_date"] = release.get("release_date")
            g["date_is_estimate"] = release.get("date_is_estimate", False)

    return page_result(page, per_page, total, groups=groups)


def game_exists(game_id):
    return fetch_one("SELECT 1 AS found FROM games WHERE id = ?", game_id) is not None


def get_price_history(game_id, days=90):
    """Price changes per offer over the last `days`, plus the price in effect at the start."""
    rows = fetch_all(
        """
        WITH window_start AS (SELECT DATEADD(DAY, -?, SYSUTCDATETIME()) AS since)
        SELECT sp.id AS offer_id, s.slug AS store, s.name AS store_name, sp.edition_id, e.name AS edition,
               sp.condition, ps.scraped_at AS date, ps.price, ps.in_stock
        FROM store_products sp
        JOIN stores s ON s.id = sp.store_id
        LEFT JOIN game_editions e ON e.id = sp.edition_id
        JOIN price_snapshots ps ON ps.store_product_id = sp.id
        CROSS JOIN window_start w
        WHERE sp.game_id = ?
          AND (ps.scraped_at >= w.since
               OR ps.id = (SELECT TOP 1 x.id FROM price_snapshots x
                           WHERE x.store_product_id = sp.id AND x.scraped_at < w.since
                           ORDER BY x.scraped_at DESC, x.id DESC))
        ORDER BY sp.id, ps.scraped_at
        """,
        days, game_id,
    )

    offers = {}
    for r in rows:
        offer = offers.setdefault(r["offer_id"], {
            "offer_id": r["offer_id"], "store": r["store"], "store_name": r["store_name"],
            "edition_id": r["edition_id"], "edition": r["edition"],
            "condition": r["condition"], "history": [],
        })
        offer["history"].append({"date": r["date"], "price": r["price"], "in_stock": r["in_stock"]})

    return list(offers.values())
