"""/api/favorites: the logged-in user's favourite editions (ids; the cards come from /api/games/editions)."""
from flask import Blueprint, jsonify, request

from app.routes.auth import current_user, login_required
from app.services import favorite_service
from app.services.favorite_service import FavoriteError

bp = Blueprint("favorites", __name__, url_prefix="/api/favorites")


@bp.errorhandler(FavoriteError)
def favorite_error(e):
    return jsonify(error=e.code), e.status


@bp.get("")
@login_required
def list_ids():
    return jsonify(favorite_service.list_ids(current_user()["id"]))


@bp.put("/<int:edition_id>")
@login_required
def add(edition_id):
    return jsonify(favorite_service.add(current_user()["id"], edition_id))


@bp.delete("/<int:edition_id>")
@login_required
def remove(edition_id):
    return jsonify(favorite_service.remove(current_user()["id"], edition_id))


@bp.post("/import")
@login_required
def import_from_browser():
    """{ids: [...]}: favourites kept in this browser before logging in, moved into the account."""
    ids = (request.get_json(silent=True) or {}).get("ids") or []
    return jsonify(favorite_service.import_ids(current_user()["id"], ids if isinstance(ids, list) else []))
