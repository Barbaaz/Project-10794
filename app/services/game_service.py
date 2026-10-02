import json
import re

from core.normalizer import normalize_name
from db import fetch_all, fetch_one

# A special edition whose game is a download code, not a disc ("Jogo Completo (Download Digital)")
DIGITAL_CODE = re.compile(r"download\s+digital|digital\s+download|c[oó]digo\s+(de\s+)?(download|digital|descarga)",
                          re.IGNORECASE)

# A favourite that came back in stock is flagged for this many days
RESTOCK_ALERT_DAYS = 14

# Offer columns sent to clients. The store's own crossed-out price is deliberately
# not included: "was_price" is only set when our price history confirms a real discount.
OFFER_COLUMNS = """
    o.store_product_id AS offer_id, o.game_id, o.edition_id,
    s.slug AS store, s.name AS store_name,
    o.condition, o.price, o.in_stock, o.is_preorder, o.url, o.image_url AS image, o.external_name,
    CASE WHEN o.is_discount = 1 THEN o.reference_price END AS was_price,
    o.discount_percent, o.is_discount, o.last_seen_at
"""


def search_filters(q, platform):
    """WHERE clause + params: every word of q must appear in the game's title."""
    where, params = ["EXISTS (SELECT 1 FROM store_products sp WHERE sp.game_id = g.id AND sp.is_active = 1)"], []

    for word in normalize_name(q or "").split():
        where.append("g.normalized_title LIKE ?")
        params.append(f"%{word}%")

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

    return {"page": page, "per_page": per_page, "total": total, "games": games}


def offer_summaries(game_ids):
    """{game_id: best price in stock, number of stores / editions, any real discount}"""
    if not game_ids:
        return {}

    placeholders = ",".join("?" * len(game_ids))
    rows = fetch_all(
        f"""
        SELECT game_id,
               MIN(CASE WHEN in_stock = 1 THEN price END) AS best_price,
               COUNT(DISTINCT store_id) AS stores,
               COUNT(DISTINCT edition_id) AS editions,
               CAST(MAX(CAST(is_discount AS INT)) AS BIT) AS has_discount
        FROM current_offers
        WHERE is_active = 1 AND game_id IN ({placeholders})
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

    lowest = lowest_prices(game_id)
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

    from app.services.release_service import game_release_date   # avoids a circular import
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


def lowest_prices(game_id):
    """
    {edition_id: {price, date, store, offer_id}}: the lowest price ever recorded for each
    edition, across all stores (also products no longer sold). Only new copies, and only
    while in stock: a used copy or a sold-out price isn't a price you could have paid.
    The earliest date wins a tie.
    """
    rows = fetch_all(
        """
        SELECT edition_id, price, date, store, offer_id
        FROM (
            SELECT sp.edition_id, ps.price, ps.scraped_at AS date, s.slug AS store, sp.id AS offer_id,
                   ROW_NUMBER() OVER (PARTITION BY sp.edition_id ORDER BY ps.price, ps.scraped_at) AS rn
            FROM store_products sp
            JOIN price_snapshots ps ON ps.store_product_id = sp.id
            JOIN stores s ON s.id = sp.store_id
            WHERE sp.game_id = ? AND sp.condition = 'new' AND ps.in_stock = 1
        ) x
        WHERE rn = 1
        """,
        game_id,
    )
    return {r.pop("edition_id"): r for r in rows}


def merged_into(kind, ids):
    """{old id: id now}: games / editions merged into another (pipeline/rematch.py, merged_ids)."""
    if not ids:
        return {}
    return dict((r["old_id"], r["new_id"]) for r in fetch_all(
        f"SELECT old_id, new_id FROM merged_ids WHERE kind = ? AND old_id IN ({','.join('?' * len(ids))})",
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
    placeholders = ",".join("?" * len(edition_ids))

    editions = fetch_all(
        f"""
        SELECT e.id AS edition_id, e.name AS edition, e.edition_key, g.id AS game_id, g.title,
               p.code AS console, p.name AS platform_name, g.image_url AS image
        FROM game_editions e
        JOIN games g ON g.id = e.game_id
        JOIN platforms p ON p.id = g.platform_id
        WHERE e.id IN ({placeholders})
        """,
        *edition_ids,
    )
    # Two steps on purpose (see search_offers): filter current_offers by id, not by a join
    offers = fetch_all(
        f"""
        SELECT {OFFER_COLUMNS}
        FROM current_offers o JOIN stores s ON s.id = o.store_id
        WHERE o.is_active = 1 AND o.edition_id IN ({placeholders})
        ORDER BY o.in_stock DESC, o.price
        """,
        *edition_ids,
    )
    lowest = {r.pop("edition_id"): r for r in fetch_all(
        f"""
        SELECT edition_id, price, date, store, tracked_since
        FROM (
            SELECT sp.edition_id, ps.price, ps.scraped_at AS date, s.slug AS store,
                   ROW_NUMBER() OVER (PARTITION BY sp.edition_id ORDER BY ps.price, ps.scraped_at) AS rn,
                   MIN(ps.scraped_at) OVER (PARTITION BY sp.edition_id) AS tracked_since
            FROM store_products sp
            JOIN price_snapshots ps ON ps.store_product_id = sp.id
            JOIN stores s ON s.id = sp.store_id
            WHERE sp.edition_id IN ({placeholders}) AND sp.condition = 'new' AND ps.in_stock = 1
        ) x
        WHERE rn = 1
        """,
        *edition_ids,
    )}

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
            WHERE sp.edition_id IN ({placeholders})
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
    groups = []
    for e in sorted(editions, key=lambda e: order[e["edition_id"]]):
        groups.append({
            "edition_id": e["edition_id"],
            "game_id": e["game_id"],
            "name": e["title"] if e["edition_key"] == "" else f"{e['title']} — {e['edition']}",
            "console": e["console"],
            "platform_name": e["platform_name"],
            "image": e["image"],
            "lowest_price": lowest.get(e["edition_id"]),
            "offers": [o for o in offers if o["edition_id"] == e["edition_id"]],
        })
    return groups


CATALOG_SORTS = {
    "name": "g.title, p.sort_order, CASE WHEN e.edition_key = '' THEN 0 ELSE 1 END, e.name",
    "price_asc": "ed.best_price, g.title",
    "price_desc": "ed.best_price DESC, g.title",
}


def catalog(platform=None, sort="name", page=1, per_page=48, special_only=False):
    """
    The whole catalogue: every edition with at least one offer in stock, as card groups
    (same shape as /search), one page at a time. sort: name / price_asc / price_desc.
    special_only: only editions above Standard (Deluxe, Collector's, Steelbook...). Keys are
    "" for Standard and "|Game Key Card" for a Standard that only differs in format.
    """
    order_by = CATALOG_SORTS.get(sort, CATALOG_SORTS["name"])
    in_stock_editions = """
        WITH offers AS (
            SELECT sp.edition_id, last.price
            FROM store_products sp
            CROSS APPLY (SELECT TOP 1 price, in_stock FROM price_snapshots ps
                         WHERE ps.store_product_id = sp.id ORDER BY ps.scraped_at DESC, ps.id DESC) last
            WHERE sp.is_active = 1 AND last.in_stock = 1 AND sp.edition_id IS NOT NULL
        ),
        ed AS (SELECT edition_id, MIN(price) AS best_price FROM offers GROUP BY edition_id)
    """
    filters = "(? IS NULL OR p.code = ?)"
    if special_only:
        filters += " AND e.edition_key <> '' AND e.edition_key NOT LIKE '|%'"

    total = fetch_one(
        f"""{in_stock_editions}
        SELECT COUNT(*) AS total FROM ed
        JOIN game_editions e ON e.id = ed.edition_id
        JOIN games g ON g.id = e.game_id
        JOIN platforms p ON p.id = g.platform_id
        WHERE {filters}""",
        platform, platform,
    )["total"]

    page_editions = fetch_all(
        f"""{in_stock_editions}
        SELECT e.id AS edition_id, e.name AS edition, e.edition_key, g.id AS game_id, g.title,
               p.code AS console, p.name AS platform_name
        FROM ed
        JOIN game_editions e ON e.id = ed.edition_id
        JOIN games g ON g.id = e.game_id
        JOIN platforms p ON p.id = g.platform_id
        WHERE {filters}
        ORDER BY {order_by}
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY""",
        platform, platform, (page - 1) * per_page, per_page,
    )

    groups = []
    if page_editions:
        ids = [e["edition_id"] for e in page_editions]
        # Two steps on purpose (see search_offers): filter current_offers by id, not by a join
        offers = fetch_all(
            f"""
            SELECT {OFFER_COLUMNS}
            FROM current_offers o JOIN stores s ON s.id = o.store_id
            WHERE o.is_active = 1 AND o.in_stock = 1 AND o.edition_id IN ({",".join("?" * len(ids))})
            ORDER BY o.price
            """,
            *ids,
        )
        for e in page_editions:
            groups.append({
                "edition_id": e["edition_id"],
                "game_id": e["game_id"],
                "name": e["title"] if e["edition_key"] == "" else f"{e['title']} — {e['edition']}",
                "console": e["console"],
                "platform_name": e["platform_name"],
                "offers": [o for o in offers if o["edition_id"] == e["edition_id"]],
            })

        # Games not out yet: their release date, so the card can say so
        from app.services.release_service import game_release_dates   # avoids a circular import
        pre_order_games = {g["game_id"] for g in groups if g["offers"] and all(o["is_preorder"] for o in g["offers"])}
        dates = game_release_dates(list(pre_order_games))
        for g in groups:
            g["is_preorder"] = g["game_id"] in pre_order_games
            release = dates.get(g["game_id"]) or {}
            g["release_date"] = release.get("release_date")
            g["date_is_estimate"] = release.get("date_is_estimate", False)

    pages = max(1, -(-total // per_page))
    return {"page": page, "per_page": per_page, "pages": pages, "total": total, "groups": groups}


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


def search_offers(q, limit=60):
    """
    For the web page: one group per game edition with its in-stock offers.
    Shape kept from the old live-scraping /search: [{name, console, offers: [...]}]
    """
    where, params = search_filters(q, None)

    # Two steps on purpose: joining current_offers to a subquery makes SQL Server
    # recompute the view per game (30 s instead of 0.1 s)
    game_ids = [r["id"] for r in fetch_all(
        f"""
        SELECT TOP {int(limit)} g.id FROM games g JOIN platforms p ON p.id = g.platform_id
        WHERE {where} ORDER BY g.title
        """,
        *params,
    )]
    if not game_ids:
        return []

    placeholders = ",".join("?" * len(game_ids))
    rows = fetch_all(
        f"""
        SELECT g.title, p.code AS console, p.name AS platform_name, e.name AS edition, e.edition_key, {OFFER_COLUMNS}
        FROM current_offers o
        JOIN games g ON g.id = o.game_id
        JOIN platforms p ON p.id = g.platform_id
        JOIN game_editions e ON e.id = o.edition_id
        JOIN stores s ON s.id = o.store_id
        WHERE o.is_active = 1 AND o.in_stock = 1 AND o.game_id IN ({placeholders})
        ORDER BY g.title, p.code, CASE WHEN e.edition_key = '' THEN 0 ELSE 1 END, e.name, o.price
        """,
        *game_ids,
    )

    groups = {}
    for r in rows:
        name = r["title"] if r["edition_key"] == "" else f"{r['title']} — {r['edition']}"
        group = groups.setdefault(r["edition_id"], {
            "name": name, "console": r["console"], "platform_name": r["platform_name"],
            "game_id": r["game_id"], "edition_id": r["edition_id"], "offers": [],
        })
        group["offers"].append(r)

    return list(groups.values())
