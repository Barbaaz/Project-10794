from flask import Blueprint, jsonify, request

from app.routes.params import int_arg, page_args
from app.services import price_service

bp = Blueprint("prices", __name__, url_prefix="/api")


@bp.get("/discounts/featured")
def featured_discounts():
    return jsonify(price_service.featured_discounts(
        limit=int_arg("limit", 12, minimum=1, maximum=50),
        min_percent=int_arg("min_percent", 10, minimum=0, maximum=100),
    ))


@bp.get("/discounts")
def list_discounts():
    page, per_page = page_args()
    return jsonify(price_service.list_discounts(
        platform=request.args.get("platform"),
        min_percent=int_arg("min_percent", 0, minimum=0, maximum=100),
        page=page,
        per_page=per_page,
    ))
