from flask import Blueprint, abort, jsonify, request

from app.routes.params import int_arg, page_args
from app.services import game_service

bp = Blueprint("games", __name__, url_prefix="/api/games")


@bp.get("")
def list_games():
    page, per_page = page_args()
    return jsonify(game_service.list_games(
        q=request.args.get("q"),
        platform=request.args.get("platform"),
        page=page,
        per_page=per_page,
    ))


@bp.get("/catalog")
def catalog():
    """
    /api/games/catalog?platform=PS5&sort=name|price_asc|price_desc&page=1&per_page=48&editions=special&q=zelda&store=darty
    editions=special: only editions above Standard (Deluxe, Collector's...)
    q: search words (all of them in the title); store: only editions that store has in stock
    """
    sort = request.args.get("sort", "name")
    if sort not in game_service.CATALOG_SORTS:
        abort(400, description=f"'sort' must be one of: {', '.join(game_service.CATALOG_SORTS)}")
    page = int_arg("page", 1, minimum=1)
    per_page = int_arg("per_page", 48, minimum=1, maximum=100)
    special_only = request.args.get("editions") == "special"
    return jsonify(game_service.catalog(
        request.args.get("platform") or None, sort, page, per_page, special_only,
        q=request.args.get("q") or None, store=request.args.get("store") or None,
    ))


@bp.get("/editions")
def editions():
    """/api/games/editions?ids=12,34: these editions with their offers (the favourites tab)."""
    try:
        ids = [int(i) for i in request.args.get("ids", "").split(",") if i.strip()]
    except ValueError:
        abort(400, description="'ids' must be a comma-separated list of numbers")
    if len(ids) > 200:
        abort(400, description="at most 200 ids")
    # Favourites saved before two editions were merged: answer with the edition now, and say
    # which saved id it replaces (merged_from) so the page can update what it saved
    merged = game_service.merged_into("edition", ids)
    groups = game_service.editions_with_offers(list(dict.fromkeys(merged.get(i, i) for i in ids)))
    for group in groups:
        old = [o for o, n in merged.items() if n == group["edition_id"]]
        if old:
            group["merged_from"] = old
    return jsonify(groups)


@bp.get("/<int:game_id>")
def get_game(game_id):
    game = game_service.get_game(game_id)
    if not game:
        abort(404, description="Game not found")
    return jsonify(game)


@bp.get("/<int:game_id>/prices")
def price_history(game_id):
    if not game_service.game_exists(game_id):
        abort(404, description="Game not found")
    days = int_arg("days", 90, minimum=1, maximum=3650)
    return jsonify(game_service.get_price_history(game_id, days))
