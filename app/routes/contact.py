"""The Contactos page's API and the team's view of it in /admin (app/services/contact_service.py)."""
from flask import Blueprint, jsonify, request

from app.routes.auth import current_user, moderator_required
from app.services import contact_service
from app.services.contact_service import ContactError

bp = Blueprint("contact", __name__, url_prefix="/api")


@bp.errorhandler(ContactError)
def contact_error(e):
    return jsonify(error=e.code), e.status


def body():
    return request.get_json(silent=True) or {}


@bp.post("/contact")
def send():
    """{name, email, topic, body, website (the hidden field: empty)}; logged in or not"""
    user = current_user()
    return jsonify(contact_service.send(body(), user["id"] if user else None, request.remote_addr or "?"))


@bp.get("/mod/contact")
@moderator_required
def messages():
    """?handled=1: the handled ones; else the open ones. {items, open}"""
    return jsonify(items=contact_service.messages(request.args.get("handled") == "1"), open=contact_service.open_count())


@bp.post("/mod/contact/<int:message_id>")
@moderator_required
def mark(message_id):
    """{handled: true | false}"""
    return jsonify(contact_service.mark(message_id, bool(body().get("handled")), current_user()["id"]))
