from flask import Blueprint, jsonify

from db import fetch_all

bp = Blueprint("stores", __name__, url_prefix="/api")


@bp.get("/stores")
def list_stores():
    # color_slot: fixed per store (by id, counting inactive ones too), so charts keep
    # each store's color when stores are added or switched off
    return jsonify(fetch_all("""
        SELECT slug, name, base_url, color_slot, last_updated
        FROM (
            SELECT s.slug, s.name, s.base_url, s.is_active,
                   ROW_NUMBER() OVER (ORDER BY s.id) AS color_slot,
                   (SELECT MAX(r.finished_at) FROM scrape_runs r
                    WHERE r.store_id = s.id AND r.status = 'success') AS last_updated
            FROM stores s
        ) x
        WHERE is_active = 1
        ORDER BY name
    """))


@bp.get("/platforms")
def list_platforms():
    # Only platforms with something on sale, in display order
    return jsonify(fetch_all("""
        SELECT p.code, p.name FROM platforms p
        WHERE EXISTS (SELECT 1 FROM store_products sp WHERE sp.platform_id = p.id AND sp.is_active = 1)
        ORDER BY p.sort_order, p.name
    """))
