"""Ratings between users after a purchase (app/services/rating_service.py), and public profiles."""
from flask import Blueprint, abort, jsonify, request

from app.routes.auth import current_user, login_required
from app.services import rating_service
from app.services.rating_service import RatingError

bp = Blueprint("ratings", __name__, url_prefix="/api")


@bp.errorhandler(RatingError)
def rating_error(e):
    return jsonify(error=e.code), e.status


def body():
    return request.get_json(silent=True) or {}


@bp.get("/ratings/pending")
@login_required
def pending():
    """The completed purchases the user still has to rate (`overdue` ones block buying / selling)."""
    return jsonify(rating_service.pending(current_user()["id"]))


@bp.post("/conversations/<int:conversation_id>/rating")
@login_required
def rate(conversation_id):
    """{stars: 1–5, comment?}: rate the other side of a completed purchase (or change it)."""
    data = body()
    return jsonify(rating_service.rate(current_user()["id"], conversation_id, data.get("stars"), data.get("comment")))


@bp.post("/ratings/<int:rating_id>/reply")
@login_required
def reply(rating_id):
    return jsonify(rating_service.reply(current_user()["id"], rating_id, body().get("reply")))


@bp.get("/users/<username>")
def profile(username):
    """A user's public profile: rating, the ratings they got, their listings (never the email)."""
    user = rating_service.profile(username)
    if user is None:
        abort(404, description="not_found")
    return jsonify(user)
