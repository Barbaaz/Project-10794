from core.normalizer import normalize_name
from db import fetch_all, fetch_one

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
        SELECT g.id, g.title, p.code AS platform, p.name AS platform_name, g.image_url AS image
        FROM games g JOIN platforms p ON p.id = g.platform_id
        WHERE g.id = ?
        """,
        game_id,
    )
    if not game:
        return None

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

    for edition in editions:
        edition["offers"] = [o for o in offers if o["edition_id"] == edition["id"]]
        in_stock = [o["price"] for o in edition["offers"] if o["in_stock"]]
        edition["best_price"] = min(in_stock) if in_stock else None
        edition["lowest_price"] = lowest.get(edition["id"])

    # Editions whose products all left the stores have nothing to show
    game["editions"] = [e for e in editions if e["offers"]]

    from app.services.release_service import game_release_date   # avoids a circular import
    release = game_release_date(game_id) or {}
    game["release_date"] = release.get("release_date")
    game["date_is_estimate"] = release.get("date_is_estimate", False)
    return game


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
