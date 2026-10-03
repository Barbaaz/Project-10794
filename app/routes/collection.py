"""/api/collection: the logged-in user's game collection and wishlist (app/services/collection_service.py)."""
from flask import Blueprint, abort, jsonify, request

from app.routes.auth import current_user, login_required
from app.services import collection_service
from app.services.collection_service import CollectionError

bp = Blueprint("collection", __name__, url_prefix="/api")

EDITABLE = ("format", "status", "hours", "achievements", "achievements_total", "notes")


@bp.errorhandler(CollectionError)
def collection_error(e):
    return jsonify(error=e.code), e.status


def body():
    return request.get_json(silent=True) or {}


@bp.get("/collection")
@login_required
def mine():
    """{items, stats, public}"""
    return jsonify(collection_service.collection(current_user()["id"]))


@bp.get("/collection/deals")
@login_required
def deals():
    """{count, items}: wishes that are a good deal now (the 📚 header button's badge)"""
    return jsonify(collection_service.good_deals(current_user()["id"]))


@bp.get("/collection/editions")
@login_required
def item_ids():
    """{edition_id: {owned?: item id, wishlist?: item id}}"""
    return jsonify(collection_service.item_ids(current_user()["id"]))


@bp.post("/collection")
@login_required
def add():
    """{edition_id, kind: owned | wishlist, format?, status?, hours?, notes?} → {id}"""
    data = body()
    item_id = collection_service.add(current_user()["id"], data.get("edition_id"), data.get("kind"),
                                     **{k: data[k] for k in EDITABLE if k in data})
    return jsonify(id=item_id), 201


@bp.post("/collection/import")
@login_required
def import_from_browser():
    """{ids: [...]}: favourites an old browser kept (before accounts), onto the wishlist → {added}"""
    ids = body().get("ids") or []
    return jsonify(collection_service.add_wishes(current_user()["id"], ids if isinstance(ids, list) else []))


@bp.patch("/collection/<int:item_id>")
@login_required
def update(item_id):
    """{format?, status?, hours?, notes?, kind: owned (a wishlist item bought)}"""
    data = body()
    changes = {k: data[k] for k in (*EDITABLE, "kind") if k in data}
    return jsonify(id=collection_service.update(current_user()["id"], item_id, changes))


@bp.delete("/collection/<int:item_id>")
@login_required
def remove(item_id):
    return jsonify(collection_service.remove(current_user()["id"], item_id))


@bp.put("/collection/settings")
@login_required
def settings():
    """{public: true | false}: show the collection on the user's profile"""
    return jsonify(collection_service.set_public(current_user()["id"], body().get("public")))


@bp.get("/users/<username>/collection")
def public(username):
    """A user's collection, when they made it public."""
    data = collection_service.public_collection(username)
    if data is None:
        abort(404, description="not_found")
    return jsonify(data)
