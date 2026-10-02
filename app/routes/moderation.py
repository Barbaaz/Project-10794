"""
Reports (any logged-in user) and the moderators' tools (role moderator or admin; naming
moderators: admin). See app/services/moderation_service.py.
"""
from flask import Blueprint, jsonify, request

from app.routes.auth import admin_required, current_user, login_required, moderator_required
from app.services import moderation_service
from app.services.moderation_service import ModerationError

bp = Blueprint("moderation", __name__, url_prefix="/api")


@bp.errorhandler(ModerationError)
def moderation_error(e):
    return jsonify(error=e.code), e.status


def body():
    return request.get_json(silent=True) or {}


@bp.post("/reports")
@login_required
def report():
    """{kind: listing | user | rating, target_id, reason, details?}"""
    data = body()
    return jsonify(moderation_service.report(current_user()["id"], data.get("kind"), data.get("target_id"),
                                             data.get("reason"), data.get("details"))), 201


@bp.get("/mod/reports")
@moderator_required
def open_reports():
    return jsonify(moderation_service.open_reports())


@bp.post("/mod/actions")
@moderator_required
def act():
    """{action: hide_listing | restore_listing | hide_rating | restore_rating | block_user | unblock_user
    | dismiss (target_id = the report), target_id, note?}"""
    data = body()
    return jsonify(moderation_service.act(current_user()["id"], data.get("action"), data.get("target_id"),
                                          data.get("note")))


@bp.get("/mod/problems")
@moderator_required
def problems():
    return jsonify(moderation_service.problem_purchases())


@bp.get("/mod/conversations/<int:conversation_id>")
@moderator_required
def conversation(conversation_id):
    return jsonify(moderation_service.conversation_messages(conversation_id))


@bp.get("/mod/log")
@moderator_required
def log():
    return jsonify(moderation_service.log())


@bp.get("/mod/staff")
@admin_required
def staff():
    return jsonify(moderation_service.staff())


@bp.post("/mod/staff")
@admin_required
def set_role():
    """{username, role: moderator | user}"""
    data = body()
    return jsonify(moderation_service.set_role(current_user()["id"], data.get("username"), data.get("role")))
