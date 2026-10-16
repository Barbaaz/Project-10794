"""/api/push: push notifications on this device (app/services/push_service.py)."""
from flask import Blueprint, jsonify, request

from app.routes.auth import current_user, login_required
from app.services import push_service
from app.services.push_service import PushError

bp = Blueprint("push", __name__, url_prefix="/api")

@bp.errorhandler(PushError)
def push_error(e):
    return jsonify(error=e.code), e.status


def body():
    return request.get_json(silent=True) or {}


@bp.get("/push/key")
def key():
    """{key}: the site's public key, for pushManager.subscribe()"""
    return jsonify(key=push_service.public_key())


@bp.post("/push/subscribe")
@login_required
def subscribe():
    """The browser's PushSubscription as JSON: {endpoint, keys: {p256dh, auth}}"""
    return jsonify(push_service.subscribe(current_user()["id"], body()))


@bp.post("/push/unsubscribe")
@login_required
def unsubscribe():
    """{endpoint}: this device stops getting them"""
    return jsonify(push_service.unsubscribe(current_user()["id"], body().get("endpoint")))


@bp.post("/push/test")
@login_required
def test():
    """{sent}: a notification to each of the user's devices, to see it works"""
    return jsonify(sent=push_service.send_test(current_user()["id"]))
