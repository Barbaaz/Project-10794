"""Following other users and comparing collections (app/services/follow_service.py)."""
from flask import Blueprint, jsonify

from app.routes.auth import current_user, login_required
from app.services import follow_service
from app.services.follow_service import FollowError

bp = Blueprint("follows", __name__, url_prefix="/api")


@bp.errorhandler(FollowError)
def follow_error(e):
    return jsonify(error=e.code), e.status


@bp.get("/users/<username>/follows")
def counts(username):
    """{followers, following, followed}: the profile's counts, and whether the visitor follows them"""
    user = current_user()
    return jsonify(follow_service.counts(username, user["id"] if user else None))


@bp.post("/users/<username>/follow")
@login_required
def follow(username):
    return jsonify(follow_service.follow(current_user()["id"], username))


@bp.delete("/users/<username>/follow")
@login_required
def unfollow(username):
    return jsonify(follow_service.unfollow(current_user()["id"], username))


@bp.get("/following")
@login_required
def following():
    """[{username, display_name, collection_public}]: who the user follows (only they see it)"""
    return jsonify(follow_service.following(current_user()["id"]))


@bp.get("/users/<username>/compare")
@login_required
def compare(username):
    """The user's collection beside theirs (theirs public) → {me, them, both, only_me, only_them}"""
    return jsonify(follow_service.compare(current_user()["id"], username))
