"""
Reports (any logged-in user) and the moderators' tools (role moderator or admin; naming
moderators: admin). See app/services/moderation_service.py.
"""
from flask import Blueprint, jsonify, request

from app.routes.auth import admin_required, current_user, login_required, moderator_required
from app.services import match_service, moderation_service
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


# --- fixing wrong matches (app/services/match_service.py) -------------------------------

@bp.get("/mod/matches")
@moderator_required
def find_matches():
    """?q=words: games with their editions and store products."""
    return jsonify(match_service.find(request.args.get("q", "")))


@bp.post("/mod/matches")
@moderator_required
def move_products():
    """{product_ids, edition_id} or {product_ids, game_id, new_edition}: move and pin them there."""
    data = body()
    edition_id = match_service.move(current_user()["id"], data.get("product_ids"), data.get("edition_id"),
                                    data.get("game_id"), data.get("new_edition"))
    return jsonify(edition_id=edition_id)


@bp.get("/mod/duplicates")
@moderator_required
def duplicates():
    """Possible duplicate games (same platform, same IGDB entry): [{platform, a, b}]"""
    return jsonify(match_service.duplicates())


@bp.post("/mod/duplicates/merge")
@moderator_required
def merge_games():
    """{from_id, into_id}: every product of one game moved to the other (pinned); the first is merged."""
    data = body()
    return jsonify(match_service.merge_games(current_user()["id"], data.get("from_id"), data.get("into_id")))


@bp.post("/mod/duplicates/dismiss")
@moderator_required
def dismiss_duplicate():
    """{a, b}: not the same game; the pair leaves the list."""
    data = body()
    return jsonify(match_service.dismiss_duplicate(current_user()["id"], data.get("a"), data.get("b")))


@bp.put("/mod/games/<int:game_id>/title")
@moderator_required
def set_title(game_id):
    """{title}: the game's title corrected by hand ("" = the stores' title again)."""
    return jsonify(match_service.set_title(current_user()["id"], game_id, body().get("title")))


@bp.put("/mod/games/<int:game_id>/title-en")
@moderator_required
def set_title_en(game_id):
    """{title_en}: the game's English name ("" = show the store's title)."""
    return jsonify(match_service.set_title_en(current_user()["id"], game_id, body().get("title_en")))


@bp.get("/mod/pins")
@moderator_required
def pins():
    return jsonify(match_service.pins())


@bp.delete("/mod/pins/<int:product_id>")
@moderator_required
def unpin(product_id):
    return jsonify(match_service.unpin(current_user()["id"], product_id))
