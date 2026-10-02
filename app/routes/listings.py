"""
/api/listings: games people sell. Reading is open to everyone; creating and changing needs
a logged-in user, and only the seller changes their listing.
New listings and new photos are sent as multipart/form-data (fields + "photos" files).
"""
from flask import Blueprint, jsonify, request

from app.routes.auth import current_user, login_required
from app.routes.params import int_arg
from app.services import listing_service
from app.services.listing_service import ListingError

bp = Blueprint("listings", __name__, url_prefix="/api/listings")


@bp.errorhandler(ListingError)
def listing_error(e):
    return jsonify(error=e.code), e.status


def uploaded_photos():
    return [f.read() for f in request.files.getlist("photos") if f and f.filename]


@bp.get("")
def for_game():
    """/api/listings?game_id=12: the game's listings everyone can see."""
    return jsonify(listing_service.listings_for_game(int_arg("game_id", 0, minimum=1)))


@bp.get("/mine")
@login_required
def mine():
    return jsonify(listing_service.my_listings(current_user()["id"]))


@bp.get("/<int:listing_id>")
def get(listing_id):
    user = current_user()
    listing = listing_service.get_listing(listing_id, viewer_id=user["id"] if user else None)
    if listing is None:
        raise ListingError("not_found", 404)
    return jsonify(listing)


@bp.post("")
@login_required
def create():
    form = request.form
    listing = listing_service.create_listing(
        current_user()["id"], form.get("game_id"), form.get("edition_id"), form.get("price"),
        form.get("condition"), form.get("description"), uploaded_photos(),
    )
    return jsonify(listing), 201


@bp.patch("/<int:listing_id>")
@login_required
def update(listing_id):
    changes = request.get_json(silent=True) or {}
    return jsonify(listing_service.update_listing(current_user()["id"], listing_id, changes))


@bp.post("/<int:listing_id>/photos")
@login_required
def add_photos(listing_id):
    return jsonify(listing_service.add_photos(current_user()["id"], listing_id, uploaded_photos()))


@bp.delete("/<int:listing_id>/photos/<int:photo_id>")
@login_required
def delete_photo(listing_id, photo_id):
    return jsonify(listing_service.delete_photo(current_user()["id"], listing_id, photo_id))
