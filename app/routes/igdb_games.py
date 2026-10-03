"""/api/igdb/games: the sell form's search for games the catalogue doesn't have (app/services/igdb_game_service.py)."""
from flask import Blueprint, jsonify, request

from app.routes.auth import current_user, login_required
from app.services import igdb_game_service
from app.services.igdb_game_service import IGDBGameError

bp = Blueprint("igdb_games", __name__, url_prefix="/api/igdb")


@bp.errorhandler(IGDBGameError)
def igdb_error(e):
    return jsonify(error=e.code), e.status


@bp.get("/games")
@login_required
def search():
    """?q=words: IGDB games on our platforms [{igdb_id, name, year, cover, platforms: [{code, name}]}]"""
    return jsonify(igdb_game_service.search(request.args.get("q", "")))


@bp.post("/games")
@login_required
def create():
    """{igdb_id, platform}: the game on that platform, created if we don't have it → {game_id, edition_id}"""
    data = request.get_json(silent=True) or {}
    return jsonify(igdb_game_service.create(current_user()["id"], data.get("igdb_id"), data.get("platform")))
