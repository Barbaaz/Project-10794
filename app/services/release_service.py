"""Pre-orders and upcoming releases for the front page."""
from app.services.common import EDITION_CARD_COLUMNS, LATEST_PRICE, OFFER_COLUMNS, better_title, cached, card_group
from app.services.review_service import mark_review_scores
from app.services.tag_service import mark_historical_lows
from db import fetch_all, placeholders

# One release date per game, from what the stores announce for its products:
# a real date beats a "31/12" placeholder, then the date most stores agree on, then the earliest.
GAME_RELEASE_DATES = """
game_dates AS (
    SELECT game_id, release_date,
           CASE WHEN MONTH(release_date) = 12 AND DAY(release_date) = 31 THEN 1 ELSE 0 END AS date_is_estimate,
           COUNT(*) AS stores
    FROM store_products
    WHERE is_active = 1 AND release_date IS NOT NULL AND game_id IS NOT NULL
    GROUP BY game_id, release_date
),
game_release AS (
    SELECT game_id, release_date, date_is_estimate
    FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY game_id ORDER BY date_is_estimate, stores DESC, release_date) AS rn
        FROM game_dates
    ) x
    WHERE rn = 1
)
"""


def game_release_date(game_id):
    """{release_date, date_is_estimate} for one game, or None."""
    return game_release_dates([game_id]).get(game_id)


def game_release_dates(game_ids):
    """{game_id: {release_date, date_is_estimate}} for these games (those with a known date)."""
    if not game_ids:
        return {}
    rows = fetch_all(
        f"WITH {GAME_RELEASE_DATES} SELECT game_id, release_date, CAST(date_is_estimate AS BIT) AS date_is_estimate "
        f"FROM game_release WHERE game_id IN ({placeholders(game_ids)})",
        *game_ids,
    )
    return {r.pop("game_id"): r for r in rows}


def preorders():
    """
    Games that can be pre-ordered, one group per edition with its pre-order offers
    (same shape as /search groups), soonest release first; unknown dates last.
    Sold-out pre-orders (limited editions whose allocation ran out) and pre-orders whose
    release date has passed are left out.
    """
    def compute():
        rows = fetch_all(f"""
            WITH {GAME_RELEASE_DATES}
            SELECT {EDITION_CARD_COLUMNS},
                   r.release_date AS game_release_date, CAST(r.date_is_estimate AS BIT) AS date_is_estimate,
                   {OFFER_COLUMNS}
            FROM current_offers o
            JOIN stores s ON s.id = o.store_id
            JOIN games g ON g.id = o.game_id
            JOIN platforms p ON p.id = g.platform_id
            JOIN game_editions e ON e.id = o.edition_id
            LEFT JOIN game_release r ON r.game_id = g.id
            WHERE o.is_active = 1 AND o.is_preorder = 1 AND o.condition = 'new' AND o.in_stock = 1
              -- out already: some stores keep the pre-order label after the release date
              -- (the product's own date first: a special edition can come out later than the game)
              AND COALESCE(o.release_date, r.release_date, '9999-12-31') >= CAST(SYSUTCDATETIME() AS DATE)
            ORDER BY CASE WHEN r.release_date IS NULL THEN 1 ELSE 0 END, r.release_date, g.title,
                     CASE WHEN e.edition_key = '' THEN 0 ELSE 1 END, e.name, o.price
        """)

        groups = {}
        for r in rows:
            group = groups.setdefault(r["edition_id"], card_group(
                r, [], release_date=r["game_release_date"], date_is_estimate=r["date_is_estimate"]))
            group["offers"].append(r)
        return mark_review_scores(mark_historical_lows(list(groups.values())))

    return cached("preorders", compute)


def upcoming_releases():
    """
    Games coming out from today on, one row per game (all editions), with the cheapest
    new offer in stock or on pre-order. Sorted by date; "31/12" estimates at the end.
    """
    def compute():
        rows = fetch_all(f"""
            WITH {GAME_RELEASE_DATES},
            prices AS (
                SELECT sp.game_id, sp.url, s.slug AS store, s.name AS store_name, last.price,
                       ROW_NUMBER() OVER (PARTITION BY sp.game_id ORDER BY last.price) AS rn
                FROM store_products sp
                JOIN stores s ON s.id = sp.store_id
                {LATEST_PRICE}
                -- a sold-out pre-order (e.g. a limited edition) can't be bought, so it isn't a price
                WHERE sp.is_active = 1 AND sp.condition = 'new' AND last.in_stock = 1
                  AND sp.game_id IN (SELECT game_id FROM game_release
                                     WHERE release_date >= CAST(SYSUTCDATETIME() AS DATE))
            )
            SELECT g.id AS game_id, g.title, NULLIF(g.title_en, '') AS title_en, p.code AS platform, p.name AS platform_name, g.image_url AS image,
                   r.release_date, CAST(r.date_is_estimate AS BIT) AS date_is_estimate,
                   pr.price AS best_price, pr.store, pr.store_name, pr.url,
                   (SELECT COUNT(DISTINCT sp.edition_id) FROM store_products sp
                    WHERE sp.game_id = g.id AND sp.is_active = 1) AS editions
            FROM game_release r
            JOIN games g ON g.id = r.game_id
            JOIN platforms p ON p.id = g.platform_id
            LEFT JOIN prices pr ON pr.game_id = g.id AND pr.rn = 1
            WHERE r.release_date >= CAST(SYSUTCDATETIME() AS DATE)
            ORDER BY r.date_is_estimate, r.release_date, g.title, p.sort_order
        """)
        for r in rows:
            r["title"] = better_title(r)
        return rows

    return cached("releases", compute)
