from flask import Blueprint, jsonify

from app.services.genre_service import genre_counts
from db import fetch_all

bp = Blueprint("stores", __name__, url_prefix="/api")

# A store not updated for this long is flagged (the daily run should keep it under 24 h)
STALE_AFTER_HOURS = 36


@bp.get("/stores")
def list_stores():
    """
    Active stores with their update status:
    last_updated  last successful run
    last_status   status of the latest finished run (success / warning / failed)
    last_error    its message when it wasn't a success
    is_stale      no successful run in the last STALE_AFTER_HOURS hours
    color_slot    fixed per store (by id, counting inactive ones too), so charts keep each
                  store's color when stores are added or switched off
    """
    return jsonify(fetch_all(
        """
        SELECT x.slug, x.name, x.base_url, x.color_slot, x.last_updated,
               latest.status AS last_status, latest.finished_at AS last_run_at,
               CASE WHEN latest.status <> 'success' THEN LEFT(latest.error_message, 300) END AS last_error,
               CAST(CASE WHEN x.last_updated IS NULL
                          OR x.last_updated < DATEADD(HOUR, ?, SYSUTCDATETIME()) THEN 1 ELSE 0 END AS BIT) AS is_stale
        FROM (
            SELECT s.id, s.slug, s.name, s.base_url, s.is_active,
                   ROW_NUMBER() OVER (ORDER BY s.id) AS color_slot,
                   (SELECT MAX(r.finished_at) FROM scrape_runs r
                    WHERE r.store_id = s.id AND r.status = 'success') AS last_updated
            FROM stores s
        ) x
        OUTER APPLY (
            SELECT TOP 1 r.status, r.finished_at, r.error_message
            FROM scrape_runs r
            WHERE r.store_id = x.id AND r.status <> 'running'
            ORDER BY r.id DESC
        ) latest
        WHERE x.is_active = 1
        ORDER BY x.name
        """,
        -STALE_AFTER_HOURS,
    ))


@bp.get("/platforms")
def list_platforms():
    # Only platforms with something on sale, in display order
    return jsonify(fetch_all("""
        SELECT p.code, p.name FROM platforms p
        WHERE EXISTS (SELECT 1 FROM store_products sp WHERE sp.platform_id = p.id AND sp.is_active = 1)
        ORDER BY p.sort_order, p.name
    """))


@bp.get("/genres")
def list_genres():
    """Categories with games in stock, for the catalogue's category filter: [{genre, count}]."""
    return jsonify(genre_counts())
