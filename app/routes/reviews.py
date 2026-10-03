"""Players' reviews of games, 1–10 (app/services/review_service.py)."""
from flask import Blueprint, jsonify, request

from app.routes.auth import current_user, login_required
from app.routes.params import int_arg
from app.services import review_service
from app.services.review_service import ReviewError

bp = Blueprint("reviews", __name__, url_prefix="/api/games")


@bp.errorhandler(ReviewError)
def review_error(e):
    return jsonify(error=e.code), e.status


@bp.get("/<int:game_id>/reviews")
def reviews(game_id):
    """{summary: {average, count, distribution}, mine, reviews, page, pages}; ?page=2"""
    user = current_user()
    return jsonify(review_service.reviews(game_id, user and user["id"], int_arg("page", 1, minimum=1)))


@bp.put("/<int:game_id>/reviews/mine")
@login_required
def save(game_id):
    """{score: 1–10, title?, body?}: write or change one's review of this game."""
    data = request.get_json(silent=True) or {}
    return jsonify(review_service.save(current_user()["id"], game_id, data.get("score"), data.get("title"),
                                       data.get("body")))


@bp.delete("/<int:game_id>/reviews/mine")
@login_required
def delete(game_id):
    return jsonify(review_service.delete(current_user()["id"], game_id))
