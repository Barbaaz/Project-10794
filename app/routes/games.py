from flask import Blueprint, abort, jsonify, request

from app.routes.params import choice_arg, int_arg, page_args, text_arg
from app.services import game_service

bp = Blueprint("games", __name__, url_prefix="/api/games")


@bp.get("")
def list_games():
    page, per_page = page_args()
    return jsonify(game_service.list_games(
        q=text_arg("q"),
        platform=text_arg("platform"),
        page=page,
        per_page=per_page,
    ))


@bp.get("/catalog")
def catalog():
    """
    /api/games/catalog?platform=PS5&sort=name|price_asc|price_desc&page=1&per_page=48&editions=special&q=zelda&store=cstech&genre=rpg
    editions=special: only editions above Standard (Deluxe, Collector's...)
    q: search words (all of them in the title); store: only editions that store has in stock;
    genre: only games in that category (/api/genres); tags=coop,horror: only games with all of
    them (/api/tags); pegi=12: PEGI rating up to that age
    kind=hardware: consoles, controllers and headsets instead of games (or kind=console / controller / headset)
    """
    sort = choice_arg("sort", "name", game_service.CATALOG_SORTS)
    page = int_arg("page", 1, minimum=1)
    per_page = int_arg("per_page", 48, minimum=1, maximum=100)
    special_only = request.args.get("editions") == "special"
    return jsonify(game_service.catalog(
        text_arg("platform"), sort, page, per_page, special_only, q=text_arg("q"), store=text_arg("store"),
        genre=text_arg("genre"),
        tags=[t for t in (text_arg("tags") or "").split(",") if t][:5],
        pegi=int_arg("pegi", None),
        kind=choice_arg("kind", "game", ("game", "hardware", *game_service.HARDWARE_KINDS)),
    ))


@bp.get("/editions")
def editions():
    """/api/games/editions?ids=12,34: these editions with their offers (the wishlist tab)."""
    try:
        ids = [int(i) for i in request.args.get("ids", "").split(",") if i.strip()]
    except ValueError:
        abort(400, description="'ids' must be a comma-separated list of numbers")
    if len(ids) > 200:
        abort(400, description="at most 200 ids")
    # Ids saved before two editions were merged: answer with the edition now, and say
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
