from app.services.common import (
    LATEST_PRICE, OFFER_COLUMNS, better_title, cached, card_cover, card_name, edition_en, page_result, title_en,
)
from app.services.review_service import mark_review_scores
from app.services.tag_service import mark_historical_lows
from db import fetch_all, fetch_one, placeholders


def attach_store_offers(items):
    """
    Give each featured item an `offers` list: its own offer plus the other stores' current
    offers for the same edition (new, in stock), cheapest first, so the card shows them all.
    """
    if not items:
        return items

    edition_ids = list({i["edition_id"] for i in items})
    others = fetch_all(
        f"""
        SELECT sp.id AS offer_id, sp.edition_id, s.slug AS store, s.name AS store_name, sp.condition,
               last.price, CAST(1 AS BIT) AS in_stock, sp.is_preorder, sp.url, sp.image_url AS image
        FROM store_products sp
        JOIN stores s ON s.id = sp.store_id
        {LATEST_PRICE}
        WHERE sp.edition_id IN ({placeholders(edition_ids)}) AND sp.is_active = 1 AND sp.condition = 'new' AND last.in_stock = 1
        ORDER BY last.price
        """,
        *edition_ids,
    )

    for item in items:
        # the card's name in both languages ("Title — Edition")
        item["name"] = card_name(better_title(item), item["edition_key"], item["edition"])
        item["name_en"] = card_name(title_en(item), item["edition_key"], edition_en(item["edition"]))
        item["cover"] = card_cover(item)
        own = {k: item[k] for k in ("offer_id", "store", "store_name", "condition", "price", "in_stock",
                                    "is_preorder", "url", "image") if k in item}
        own.update(was_price=item.get("was_price"), discount_percent=item.get("discount_percent"))
        item["offers"] = [own] + [o for o in others
                                  if o["edition_id"] == item["edition_id"] and o["offer_id"] != item["offer_id"]]
    return mark_review_scores(mark_historical_lows(items))


def featured_discounts(limit=12, min_percent=10, platform=None):
    """
    Front page: the biggest real discounts, one offer per game edition (the cheapest),
    new copies in stock only, optionally for one platform (so a filtered list still has
    `limit` games). Cached for a few minutes.
    """
    return cached(("featured", limit, min_percent, platform),
                  lambda: attach_store_offers(_featured_discounts(limit, min_percent, platform)))


def _featured_discounts(limit, min_percent, platform):
    return fetch_all(
        f"""
        WITH ranked AS (
            SELECT o.*, ROW_NUMBER() OVER (PARTITION BY o.edition_id ORDER BY o.price, o.discount_percent DESC) AS rn
            FROM current_offers o
            WHERE o.is_discount = 1 AND o.is_active = 1 AND o.in_stock = 1
              AND o.condition = 'new' AND o.discount_percent >= ?
        )
        SELECT TOP ({int(limit)}) g.title, g.title_en, g.cover_image_id, p.code AS platform, p.name AS platform_name,
               e.name AS edition, e.edition_key, {OFFER_COLUMNS}
        FROM ranked o
        JOIN stores s ON s.id = o.store_id
        JOIN games g ON g.id = o.game_id
        JOIN platforms p ON p.id = g.platform_id
        JOIN game_editions e ON e.id = o.edition_id
        WHERE o.rn = 1 AND (? IS NULL OR p.code = ?)
        ORDER BY o.discount_percent DESC, o.price
        """,
        min_percent, platform, platform,
    )


def best_store_deals(limit=12, min_percent=15, max_percent=60, platform=None):
    """
    Front page while there are no real discounts yet: editions where the cheapest store is
    clearly cheaper than the next cheapest store, same day, new copies in stock.
    Not a discount claim, a comparison between stores ("-25% vs outras lojas").
    Gaps above max_percent are left out: they're more often two different products matched
    together than a real bargain.
    """
    return cached(("deals", limit, min_percent, max_percent, platform),
                  lambda: attach_store_offers(_best_store_deals(limit, min_percent, max_percent, platform)))


def _best_store_deals(limit, min_percent, max_percent, platform):
    return fetch_all(
        f"""
        WITH offers AS (
            SELECT sp.id AS offer_id, sp.edition_id, sp.store_id, last.price
            FROM store_products sp {LATEST_PRICE}
            WHERE sp.is_active = 1 AND sp.condition = 'new' AND last.in_stock = 1 AND sp.edition_id IS NOT NULL
        ),
        -- the cheapest offer of each store, then the stores ranked by price
        per_store AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY edition_id, store_id ORDER BY price) AS store_rn
            FROM offers
        ),
        ranked AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY edition_id ORDER BY price) AS rn
            FROM per_store WHERE store_rn = 1
        ),
        gaps AS (
            SELECT a.offer_id, a.edition_id, a.price, b.price AS next_price, b.store_id AS next_store_id,
                   CAST(ROUND(100.0 * (b.price - a.price) / b.price, 0) AS INT) AS savings_percent
            FROM ranked a JOIN ranked b ON b.edition_id = a.edition_id AND b.rn = 2
            WHERE a.rn = 1
        )
        SELECT TOP ({int(limit)})
               g.title, g.title_en, g.cover_image_id, p.code AS platform, p.name AS platform_name, e.name AS edition, e.edition_key,
               sp.id AS offer_id, sp.game_id, sp.edition_id, s.slug AS store, s.name AS store_name,
               sp.condition, gap.price, CAST(1 AS BIT) AS in_stock, sp.is_preorder, sp.url,
               sp.image_url AS image, sp.external_name,
               gap.next_price, ns.slug AS next_store, gap.savings_percent
        FROM gaps gap
        JOIN store_products sp ON sp.id = gap.offer_id
        JOIN stores s ON s.id = sp.store_id
        JOIN stores ns ON ns.id = gap.next_store_id
        JOIN games g ON g.id = sp.game_id
        JOIN platforms p ON p.id = g.platform_id
        JOIN game_editions e ON e.id = sp.edition_id
        WHERE gap.savings_percent BETWEEN ? AND ? AND (? IS NULL OR p.code = ?)
        ORDER BY gap.savings_percent DESC, gap.price
        """,
        min_percent, max_percent, platform, platform,
    )


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

    return page_result(page, per_page, total, offers=offers)
