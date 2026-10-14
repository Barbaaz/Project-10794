"""Pre-orders and upcoming releases for the front page."""
from app.services.common import EDITION_CARD_COLUMNS, LATEST_PRICE, OFFER_COLUMNS, cached, card_cover, card_group
from app.services.review_service import mark_review_scores
from app.services.tag_service import mark_historical_lows
from db import fetch_all, placeholders

# One release date per game, from what the stores announce for its products:
# a real date beats a "31/12" placeholder, then the date most stores agree on, then the earliest.
GAME_RELEASE_DATES = """
game_dates AS (
    SELECT game_id, release_date,
           (EXTRACT(MONTH FROM release_date) = 12 AND EXTRACT(DAY FROM release_date) = 31) AS date_is_estimate,
           COUNT(*) AS stores
    FROM store_products
    WHERE is_active AND release_date IS NOT NULL AND game_id IS NOT NULL
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
        f"WITH {GAME_RELEASE_DATES} SELECT game_id, release_date, date_is_estimate "
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
                   r.release_date AS game_release_date, r.date_is_estimate,
                   {OFFER_COLUMNS}
            FROM current_offers o
            JOIN stores s ON s.id = o.store_id
            JOIN games g ON g.id = o.game_id
            JOIN platforms p ON p.id = g.platform_id
            JOIN game_editions e ON e.id = o.edition_id
            LEFT JOIN game_release r ON r.game_id = g.id
            WHERE o.is_active AND o.is_preorder AND o.condition = 'new' AND o.in_stock AND g.kind = 'game'
              -- out already: some stores keep the pre-order label after the release date
              -- (the product's own date first: a special edition can come out later than the game)
              AND COALESCE(o.release_date, r.release_date, '9999-12-31') >= CAST(utcnow() AS date)
            ORDER BY CASE WHEN r.release_date IS NULL THEN 1 ELSE 0 END, r.release_date, g.title,
                     CASE WHEN e.edition_key = '' THEN 0 ELSE 1 END, e.name, e.id, o.price, o.store_product_id
        """)

        groups, first = {}, {}
        for r in rows:
            group = groups.setdefault(r["edition_id"], card_group(
                r, [], release_date=r["game_release_date"], date_is_estimate=r["date_is_estimate"]))
            first.setdefault(r["edition_id"], r)
            group["offers"].append(r)
        for edition_id, group in groups.items():          # the picture by store, now the offers are in
            group["cover"] = card_cover(first[edition_id], group["offers"])
        return mark_review_scores(mark_historical_lows(list(groups.values())))

    return cached("preorders", compute)


def upcoming_releases():
    """
    Games coming out from today on, as cards (same shape as /preorders): one per game, its Standard
    edition (else its cheapest), with the new offers in stock or on pre-order. Each also has
    release_date / date_is_estimate, `editions` (how many the game has), `hypes` (IGDB users following
    it) and `wishes` (our users wishing for it): Lançamentos' most anticipated and its calendar
    (user, 2026-10-14). Sorted by date; "31/12" estimates at the end.
    """
    def compute():
        games = fetch_all(f"""
            WITH {GAME_RELEASE_DATES},
            editions AS (
                SELECT sp.game_id, sp.edition_id, MIN(CASE WHEN last.in_stock THEN last.price END) AS best
                FROM store_products sp
                {LATEST_PRICE}
                WHERE sp.is_active AND sp.condition = 'new' AND sp.edition_id IS NOT NULL
                  AND sp.game_id IN (SELECT game_id FROM game_release WHERE release_date >= CAST(utcnow() AS date))
                GROUP BY sp.game_id, sp.edition_id
            ),
            picked AS (
                SELECT ed.*, COUNT(*) OVER (PARTITION BY ed.game_id) AS editions,
                       ROW_NUMBER() OVER (PARTITION BY ed.game_id
                                          ORDER BY CASE WHEN e.edition_key = '' THEN 0 ELSE 1 END, ed.best NULLS LAST,
                                                   ed.edition_id) AS rn
                FROM editions ed
                JOIN game_editions e ON e.id = ed.edition_id
            )
            SELECT {EDITION_CARD_COLUMNS}, r.release_date, r.date_is_estimate, pk.editions,
                   COALESCE(g.hypes, 0) AS hypes,
                   (SELECT COUNT(DISTINCT ci.user_id) FROM collection_items ci
                    WHERE ci.kind = 'wishlist' AND ci.game_id = g.id) AS wishes
            FROM picked pk
            JOIN game_release r ON r.game_id = pk.game_id
            JOIN games g ON g.id = pk.game_id
            JOIN platforms p ON p.id = g.platform_id
            JOIN game_editions e ON e.id = pk.edition_id
            WHERE pk.rn = 1 AND r.release_date >= CAST(utcnow() AS date) AND g.kind = 'game'
            ORDER BY r.date_is_estimate, r.release_date, g.title, p.sort_order, g.id
        """)
        offers = {}
        ids = [g["edition_id"] for g in games]
        if ids:
            for o in fetch_all(f"""
                    SELECT {OFFER_COLUMNS}
                    FROM current_offers o
                    JOIN stores s ON s.id = o.store_id
                    WHERE o.edition_id IN ({placeholders(ids)}) AND o.is_active AND o.condition = 'new' AND o.in_stock
                    ORDER BY o.price, o.store_product_id""", *ids):
                offers.setdefault(o["edition_id"], []).append(o)
        # one card per game, whatever edition each platform shows (PC may have no Standard)
        groups = [card_group(g, offers.get(g["edition_id"], []), release_date=g["release_date"],
                             date_is_estimate=g["date_is_estimate"], editions=g["editions"], hypes=g["hypes"],
                             wishes=g["wishes"], same=g["card_key"]) for g in games]
        return mark_review_scores(mark_historical_lows(groups))

    return cached("releases", compute)
