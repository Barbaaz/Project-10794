from flask import Blueprint, jsonify, request

from app.routes.params import int_arg, page_args
from app.services import price_service, release_service

bp = Blueprint("prices", __name__, url_prefix="/api")


@bp.get("/discounts/featured")
def featured_discounts():
    return jsonify(price_service.featured_discounts(
        limit=int_arg("limit", 12, minimum=1, maximum=50),
        min_percent=int_arg("min_percent", 10, minimum=0, maximum=100),
        platform=request.args.get("platform") or None,
    ))


@bp.get("/deals")
def best_store_deals():
    """Editions clearly cheaper at one store than at the next cheapest (a comparison, not a discount)."""
    return jsonify(price_service.best_store_deals(
        limit=int_arg("limit", 12, minimum=1, maximum=50),
        min_percent=int_arg("min_percent", 15, minimum=1, maximum=100),
        platform=request.args.get("platform") or None,
    ))


@bp.get("/preorders")
def preorders():
    """Pre-order games, one group per edition, soonest release first."""
    platform = request.args.get("platform")
    groups = release_service.preorders()
    return jsonify([g for g in groups if not platform or g["console"] == platform])


@bp.get("/releases")
def upcoming_releases():
    """Games coming out from today on, one per game, by release date."""
    platform = request.args.get("platform")
    games = release_service.upcoming_releases()
    return jsonify([g for g in games if not platform or g["platform"] == platform])


@bp.get("/discounts")
def list_discounts():
    page, per_page = page_args()
    return jsonify(price_service.list_discounts(
        platform=request.args.get("platform"),
        min_percent=int_arg("min_percent", 0, minimum=0, maximum=100),
        page=page,
        per_page=per_page,
    ))
