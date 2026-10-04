"""
Marketplace conversations and purchase steps (app/services/chat_service.py). Everything here
needs a logged-in user, who only ever sees their own conversations.
"""
from flask import Blueprint, jsonify, request, send_from_directory

from app.routes.auth import current_user, login_required
from app.routes.params import int_arg
from app.services import chat_service
from app.services.chat_service import ChatError
from app.services.photo_storage import storage

bp = Blueprint("chat", __name__, url_prefix="/api")


@bp.errorhandler(ChatError)
def chat_error(e):
    return jsonify(error=e.code), e.status


def body():
    return request.get_json(silent=True) or {}


@bp.post("/listings/<int:listing_id>/conversation")
@login_required
def start(listing_id):
    """The Message / Buy buttons: {message?, buy?} → {id} of the conversation."""
    data = body()
    conversation_id = chat_service.start(current_user()["id"], listing_id, data.get("message"), bool(data.get("buy")))
    return jsonify(id=conversation_id)


@bp.get("/conversations")
@login_required
def conversations():
    return jsonify(chat_service.list_conversations(current_user()["id"]))


@bp.get("/conversations/unread")
@login_required
def unread():
    return jsonify(count=chat_service.unread_count(current_user()["id"]))


@bp.get("/conversations/<int:conversation_id>")
@login_required
def conversation(conversation_id):
    """?after=<message id>: only newer messages (the page refreshes with this)."""
    return jsonify(chat_service.get_conversation(current_user()["id"], conversation_id, int_arg("after", 0, minimum=0)))


@bp.post("/conversations/<int:conversation_id>/messages")
@login_required
def send(conversation_id):
    """{body} as JSON, or a form with `body` and up to 5 `photos` files."""
    if request.files:
        photos = [f.read() for f in request.files.getlist("photos") if f and f.filename]
        return jsonify(chat_service.send_message(current_user()["id"], conversation_id, request.form.get("body"), photos))
    return jsonify(chat_service.send_message(current_user()["id"], conversation_id, body().get("body")))


@bp.get("/conversations/<int:conversation_id>/photos/<int:photo_id>")
@login_required
def photo(conversation_id, photo_id):
    """A photo sent in the conversation (?thumb=1: the small one), for its two sides and moderators;
    kept only in the viewer's own browser cache."""
    user = current_user()
    key = chat_service.photo_file(user["id"], conversation_id, photo_id, thumb=request.args.get("thumb") == "1",
                                  staff=user["role"] in ("moderator", "admin"))
    response = send_from_directory(storage.root, key, max_age=7 * 24 * 3600)
    response.cache_control.public = False
    response.cache_control.private = True
    return response


@bp.post("/conversations/<int:conversation_id>/steps")
@login_required
def step(conversation_id):
    """{action: request | accept | decline | sent | received | problem | cancel}"""
    return jsonify(chat_service.deal_step(current_user()["id"], conversation_id, body().get("action")))
