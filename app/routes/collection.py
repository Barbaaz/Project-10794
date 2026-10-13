"""/api/collection: the logged-in user's game collection and wishlist (app/services/collection_service.py)."""
from flask import Blueprint, abort, jsonify, request

from app.routes.auth import current_user, login_required
from app.services import collection_service, dlc_service, psn_service, steam_service, wish_alert_service
from app.services.collection_service import CollectionError
from app.services.psn_service import PsnError
from app.services.steam_service import SteamError

bp = Blueprint("collection", __name__, url_prefix="/api")

EDITABLE = ("format", "status", "hours", "achievements", "achievements_total", "platinum", "notes")


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
    """{count, items}: wishes that are a good deal now (the header's notifications)"""
    return jsonify(collection_service.good_deals(current_user()["id"]))


@bp.get("/collection/editions")
@login_required
def item_ids():
    """{edition_id: {owned?: item id, wishlist?: item id}}"""
    return jsonify(collection_service.item_ids(current_user()["id"]))


@bp.post("/collection")
@login_required
def add():
    """{edition_id | game_id + new_edition, kind: owned | wishlist, format?, status?, hours?, notes?} → {id}
    (new_edition: an edition of the game we don't know, named by the user)"""
    data = body()
    item_id = collection_service.add(current_user()["id"], data.get("edition_id"), data.get("kind"),
                                     game_id=data.get("game_id"), new_edition=data.get("new_edition"),
                                     **{k: data[k] for k in EDITABLE if k in data})
    return jsonify(id=item_id), 201


@bp.post("/collection/import")
@login_required
def import_from_browser():
    """{ids: [...]}: favourites an old browser kept (before accounts), onto the wishlist → {added}"""
    ids = body().get("ids") or []
    return jsonify(collection_service.add_wishes(current_user()["id"], ids if isinstance(ids, list) else []))


@bp.get("/collection/steam")
@login_required
def steam_profile():
    """{profile: {steam_id, imported_at} | null}: the last import's profile, for the refresh button"""
    return jsonify(profile=steam_service.saved_profile(current_user()["id"]))


@bp.post("/collection/steam")
@login_required
def import_from_steam():
    """{profile?}: the user's Steam games into the collection (no profile: the last one again)
    → {added, updated, total, missing} (steam_service)"""
    try:
        return jsonify(steam_service.import_games(current_user()["id"], body().get("profile")))
    except SteamError as e:
        return jsonify(error=e.code), e.status


@bp.get("/collection/psn")
@login_required
def psn_profile():
    """{profile: {online_id, imported_at} | null}: the last PSN import's player, for the refresh button"""
    return jsonify(profile=psn_service.saved_profile(current_user()["id"]))


@bp.post("/collection/psn")
@login_required
def import_from_psn():
    """{name?, ps_plus?}: the user's PlayStation games and trophies into the collection (no name: the last
    one again; ps_plus: also games only played on PS Plus) → {added, updated, total, skipped, ps_plus, missing}
    (psn_service)"""
    data = body()
    try:
        return jsonify(psn_service.import_games(current_user()["id"], data.get("name"), data.get("ps_plus") is True))
    except PsnError as e:
        return jsonify(error=e.code), e.status


@bp.patch("/collection/<int:item_id>")
@login_required
def update(item_id):
    """{format?, status?, hours?, notes?, kind: owned (a wishlist item bought), edition_id | new_edition}"""
    data = body()
    changes = {k: data[k] for k in (*EDITABLE, "kind", "edition_id", "new_edition") if k in data}
    return jsonify(id=collection_service.update(current_user()["id"], item_id, changes))


@bp.get("/collection/<int:item_id>/dlc")
@login_required
def dlc(item_id):
    """{addons: [{igdb_id, name, type, cover, year}], owned: [igdb ids], no_igdb?}: the game's DLC from IGDB"""
    return jsonify(dlc_service.item_dlc(current_user()["id"], item_id))


@bp.put("/collection/<int:item_id>/dlc")
@login_required
def set_dlc(item_id):
    """{owned: [igdb ids]} → {owned, total}: the DLC the user owns"""
    return jsonify(dlc_service.set_owned(current_user()["id"], item_id, body().get("owned")))


@bp.delete("/collection/<int:item_id>")
@login_required
def remove(item_id):
    return jsonify(collection_service.remove(current_user()["id"], item_id))


@bp.get("/collection/settings")
@login_required
def get_settings():
    """{public, wish_alerts, lang}: for the settings page (/account), without loading the collection"""
    return jsonify(collection_service.settings(current_user()["id"]))


@bp.put("/collection/settings")
@login_required
def settings():
    """{public?, wish_alerts?, lang?}: show the collection on the user's profile; wishlist alerts by e-mail"""
    data = body()
    changes = {k: data[k] for k in ("public", "wish_alerts", "lang") if k in data}
    return jsonify(collection_service.set_settings(current_user()["id"], changes))


@bp.put("/collection/showcase")
@login_required
def showcase():
    """{sections: [...], favourites: [item ids]}: what the profile shows, in order, and the top 10"""
    data = body()
    return jsonify(collection_service.set_showcase(current_user()["id"], data.get("sections"), data.get("favourites")))


@bp.post("/collection/alerts-off")
def alerts_off():
    """{token}: the link in a wishlist alert e-mail switches them off, logged in or not"""
    if not wish_alert_service.switch_off(body().get("token")):
        return jsonify(error="link_invalid"), 400
    return jsonify(ok=True)


@bp.get("/users/<username>/collection")
def public(username):
    """A user's collection, when they made it public."""
    data = collection_service.public_collection(username)
    if data is None:
        abort(404, description="not_found")
    return jsonify(data)
