import time

from app.services.game_service import OFFER_COLUMNS
from db import fetch_all, fetch_one

FEATURED_CACHE_SECONDS = 600   # prices change once a day; no need to recompute on every visit
_featured_cache = {}


def featured_discounts(limit=12, min_percent=10):
    """
    Front page: the biggest real discounts, one offer per game edition (the cheapest),
    new copies in stock only. Cached for a few minutes.
    """
    key = (limit, min_percent)
    cached = _featured_cache.get(key)
    if cached and time.monotonic() - cached[0] < FEATURED_CACHE_SECONDS:
        return cached[1]

    offers = fetch_all(
        f"""
        WITH ranked AS (
            SELECT o.*, ROW_NUMBER() OVER (PARTITION BY o.edition_id ORDER BY o.price, o.discount_percent DESC) AS rn
            FROM current_offers o
            WHERE o.is_discount = 1 AND o.is_active = 1 AND o.in_stock = 1
              AND o.condition = 'new' AND o.discount_percent >= ?
        )
        SELECT TOP ({int(limit)}) g.title, p.code AS platform, p.name AS platform_name,
               e.name AS edition, e.edition_key, {OFFER_COLUMNS}
        FROM ranked o
        JOIN stores s ON s.id = o.store_id
        JOIN games g ON g.id = o.game_id
        JOIN platforms p ON p.id = g.platform_id
        JOIN game_editions e ON e.id = o.edition_id
        WHERE o.rn = 1
        ORDER BY o.discount_percent DESC, o.price
        """,
        min_percent,
    )

    _featured_cache[key] = (time.monotonic(), offers)
    return offers


def list_discounts(platform=None, min_percent=0, page=1, per_page=20):
    """Offers that are really on sale (see current_offers in database/views.sql), biggest first."""
    where = ["o.is_discount = 1", "o.is_active = 1", "o.in_stock = 1", "o.discount_percent >= ?"]
    params = [min_percent]

    if platform:
        where.append("p.code = ?")
        params.append(platform)

    sql_from = f"""
        FROM current_offers o
        JOIN stores s ON s.id = o.store_id
        JOIN games g ON g.id = o.game_id
        JOIN platforms p ON p.id = g.platform_id
        JOIN game_editions e ON e.id = o.edition_id
        WHERE {" AND ".join(where)}
    """

    total = fetch_one(f"SELECT COUNT(*) AS total {sql_from}", *params)["total"]
    offers = fetch_all(
        f"""
        SELECT g.title, p.code AS platform, e.name AS edition, {OFFER_COLUMNS}
        {sql_from}
        ORDER BY o.discount_percent DESC, o.price
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """,
        *params, (page - 1) * per_page, per_page,
    )

    return {"page": page, "per_page": per_page, "total": total, "offers": offers}
