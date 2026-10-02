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
