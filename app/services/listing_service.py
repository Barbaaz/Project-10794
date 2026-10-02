"""
The pre-owned marketplace: games people sell (Listing) with their photos.
Only the seller changes a listing. A listing always has MIN_PHOTOS..MAX_PHOTOS photos.
"""
from decimal import Decimal, InvalidOperation

from sqlalchemy import case, func, select

from app.models import NOW, Conversation, Game, GameEdition, Listing, ListingPhoto, Platform, User, fields
from app.services.common import card_group, page_result
from app.services.photo_storage import PhotoError, process_photo, storage
from app.services.rating_service import check_not_blocked, summaries
from db import json_value, session

CONDITIONS = ("new", "like_new", "good", "fair", "poor")
STATUSES = ("active", "reserved", "sold", "removed")
VISIBLE = ("active", "reserved")      # shown to everyone; sold / removed only to the seller
MIN_PHOTOS, MAX_PHOTOS = 3, 10
MIN_PRICE, MAX_PRICE = Decimal("0.50"), Decimal("10000")
MAX_DESCRIPTION = 2000

BROWSE_SORTS = ("newest", "price_asc", "price_desc")

# Listings of a blocked seller (moderation) aren't shown to anyone
SELLER_ACTIVE = Listing.user_id.in_(select(User.id).where(User.is_active))


class ListingError(Exception):
    """A problem the seller can fix; `code` is translated by the page."""

    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


# --- reading ------------------------------------------------------------------------------

def as_dicts(listings):
    """
    Listings as the API sends them: the listing, its game / edition / platform, the seller
    (with their rating; never the email) and the photos with their URLs.
    """
    ratings = summaries([l.user_id for l in listings])
    result = []
    for l in listings:
        rating, count = ratings.get(l.user_id, (None, 0))
        result.append(fields(
            l, "id", "user_id", "game_id", "edition_id", "price", "condition", "description", "status",
            "created_at", "updated_at", "sold_at",
            title=l.game.title, platform=l.game.platform.code, platform_name=l.game.platform.name,
            edition=l.edition.name if l.edition else None,
            seller_username=l.seller.username, seller_name=l.seller.display_name,
            seller_since=json_value(l.seller.created_at), seller_rating=rating, seller_rating_count=count,
            photos=[fields(p, "id", "listing_id", "position", "photo_key", "thumb_key",
                           url=storage.url(p.photo_key), thumb_url=storage.url(p.thumb_key)) for p in l.photos],
        ))
    return result


def _listings(*conditions, order_by):
    with session() as s:
        return as_dicts(s.scalars(select(Listing).where(*conditions).order_by(*order_by)).unique().all())


def listings_for_game(game_id):
    """The game's listings everyone can see (active first, cheapest first), each with its photos."""
    return _listings(Listing.game_id == game_id, Listing.status.in_(VISIBLE), SELLER_ACTIVE,
                     order_by=(case((Listing.status == "active", 0), else_=1), Listing.price))


def listings_of_user(user_id):
    """A seller's listings everyone can see (their profile page), newest first."""
    return _listings(Listing.user_id == user_id, Listing.status.in_(VISIBLE), SELLER_ACTIVE,
                     order_by=(Listing.created_at.desc(),))


def my_listings(user_id):
    """The seller's own listings (all but removed), newest first."""
    return _listings(Listing.user_id == user_id, Listing.status != "removed", order_by=(Listing.created_at.desc(),))


def get_listing(listing_id, viewer_id=None):
    """
    A listing with its photos, or None if this viewer can't see it: sold / removed listings are
    only shown to their seller and to the people who talked to the seller about them (a buyer
    can still see what they bought).
    """
    with session() as s:
        listing = s.get(Listing, listing_id)
        if not listing:
            return None
        talked = viewer_id and s.scalar(select(Conversation.id).where(
            Conversation.listing_id == listing_id, Conversation.buyer_id == viewer_id).limit(1))
        if listing.status not in VISIBLE and listing.user_id != viewer_id and not talked:
            return None
        if not listing.seller.is_active and listing.user_id != viewer_id:
            return None                       # a blocked seller's listing
        return as_dicts([listing])[0]


def browse(platform=None, sort="newest", page=1, per_page=48):
    """
    The market tab: one group per game edition users sell (a game can have several sellers),
    each with its active listings, cheapest first; editions with the newest listing first, or
    by their cheapest price. Paged by edition.
    """
    used = (select(Listing.edition_id, func.min(Listing.price).label("min_price"),
                   func.max(Listing.created_at).label("newest"))
            .where(Listing.status == "active", Listing.edition_id.is_not(None), SELLER_ACTIVE)
            .group_by(Listing.edition_id).subquery())
    editions = (select(GameEdition, Game, Platform)
                .join(used, used.c.edition_id == GameEdition.id)
                .join(Game, Game.id == GameEdition.game_id).join(Platform, Platform.id == Game.platform_id))
    if platform:
        editions = editions.where(Platform.code == platform)
    order = {"newest": (used.c.newest.desc(), Game.title), "price_asc": (used.c.min_price, Game.title),
             "price_desc": (used.c.min_price.desc(), Game.title)}[sort if sort in BROWSE_SORTS else "newest"]

    with session() as s:
        total = s.scalar(select(func.count()).select_from(editions.subquery()))
        rows = s.execute(editions.order_by(*order).offset((page - 1) * per_page).limit(per_page)).all()
        ids = [edition.id for edition, _, _ in rows]
        listings = as_dicts(s.scalars(select(Listing).where(Listing.status == "active", Listing.edition_id.in_(ids),
                                                          SELLER_ACTIVE)
                                      .order_by(Listing.price, Listing.created_at)).unique().all()) if ids else []
    groups = [card_group({"edition_id": edition.id, "game_id": game.id, "title": game.title,
                          "edition_key": edition.edition_key, "edition": edition.name,
                          "console": platform_.code, "platform_name": platform_.name},
                         [], image=game.image_url, listings=[l for l in listings if l["edition_id"] == edition.id])
              for edition, game, platform_ in rows]
    return page_result(page, per_page, total, groups=groups)


def used_summaries(edition_ids):
    """
    {edition_id: {count, price, listing_id}}: the active listings of these editions, for the
    "Used" button on catalogue cards: how many, the lowest price and that listing.
    """
    if not edition_ids:
        return {}
    ranked = select(
        Listing.edition_id, Listing.price, Listing.id,
        func.count().over(partition_by=Listing.edition_id).label("count"),
        func.row_number().over(partition_by=Listing.edition_id, order_by=(Listing.price, Listing.id)).label("rn"),
    ).where(Listing.status == "active", Listing.edition_id.in_(edition_ids), SELLER_ACTIVE).subquery()
    with session() as s:
        rows = s.execute(select(ranked).where(ranked.c.rn == 1)).all()
    return {r.edition_id: {"count": r.count, "price": json_value(r.price), "listing_id": r.id} for r in rows}


# --- changing -----------------------------------------------------------------------------

def create_listing(user_id, game_id, edition_id, price, condition, description, photos):
    """photos: the uploaded files' bytes. Returns the new listing."""
    check_not_blocked(user_id, ListingError)       # a rating overdue: rate first
    checked = _checked_fields(price, condition, description)
    game_id, edition_id = _checked_game(game_id, edition_id)
    if not MIN_PHOTOS <= len(photos) <= MAX_PHOTOS:
        raise ListingError("photo_count")
    processed = [_process(data) for data in photos]   # all checked before anything is saved

    saved = []
    try:
        with session() as s:
            listing = Listing(user_id=user_id, game_id=game_id, edition_id=edition_id, **checked)
            s.add(listing)
            s.flush()
            saved = _store_photos(listing, processed, first_position=0)
            listing_id = listing.id
    except Exception:
        for key in saved:             # the listing wasn't saved: don't keep its files
            storage.delete(key)
        raise
    return get_listing(listing_id, viewer_id=user_id)


def update_listing(user_id, listing_id, changes):
    """The seller changes price / condition / description / status."""
    with session() as s:
        listing = _own_listing(s, user_id, listing_id)
        if listing.removed_by_moderator:
            raise ListingError("removed_by_moderator", 403)     # only a moderator can bring it back
        checked = _checked_fields(changes.get("price", listing.price), changes.get("condition", listing.condition),
                                  changes.get("description", listing.description))
        status = changes.get("status", listing.status)
        if status not in STATUSES:
            raise ListingError("status_invalid")
        for name, value in checked.items():
            setattr(listing, name, value)
        if status == "sold" and not listing.sold_at:
            listing.sold_at = NOW
        elif status != "sold":
            listing.sold_at = None
        listing.status, listing.updated_at = status, NOW
    return get_listing(listing_id, viewer_id=user_id)


def add_photos(user_id, listing_id, photos):
    with session() as s:
        listing = _own_listing(s, user_id, listing_id)
        if len(listing.photos) + len(photos) > MAX_PHOTOS:
            raise ListingError("photo_count")
    processed = [_process(data) for data in photos]
    saved = []
    try:
        with session() as s:
            listing = s.get(Listing, listing_id)
            first = max((p.position for p in listing.photos), default=-1) + 1
            saved = _store_photos(listing, processed, first_position=first)
    except Exception:
        for key in saved:
            storage.delete(key)
        raise
    return get_listing(listing_id, viewer_id=user_id)


def delete_photo(user_id, listing_id, photo_id):
    with session() as s:
        listing = _own_listing(s, user_id, listing_id)
        photo = next((p for p in listing.photos if p.id == photo_id), None)
        if photo is None:
            raise ListingError("not_found", 404)
        if len(listing.photos) <= MIN_PHOTOS:
            raise ListingError("photo_count")
        keys = photo.photo_key, photo.thumb_key
        listing.photos.remove(photo)          # delete-orphan: the row goes too
    for key in keys:
        storage.delete(key)
    return get_listing(listing_id, viewer_id=user_id)


# --- helpers ------------------------------------------------------------------------------

def _checked_fields(price, condition, description):
    try:
        price = Decimal(str(price)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ListingError("price_invalid")
    if not MIN_PRICE <= price <= MAX_PRICE:
        raise ListingError("price_invalid")
    if condition not in CONDITIONS:
        raise ListingError("condition_invalid")
    description = (description or "").strip() or None
    if description and len(description) > MAX_DESCRIPTION:
        raise ListingError("description_long")
    return {"price": price, "condition": condition, "description": description}


def _checked_game(game_id, edition_id):
    try:
        game_id = int(game_id)
        edition_id = int(edition_id) if edition_id not in (None, "") else None
    except (TypeError, ValueError):
        raise ListingError("game_invalid")
    with session() as s:
        if not s.get(Game, game_id):
            raise ListingError("game_invalid")
        edition = s.get(GameEdition, edition_id) if edition_id is not None else None
        if edition_id is not None and (edition is None or edition.game_id != game_id):
            raise ListingError("edition_invalid")
    return game_id, edition_id


def _store_photos(listing, processed, first_position):
    """
    Store the processed photos' files and add them to the listing (saved with the caller's
    session). Returns the stored keys, so the caller can delete the files if saving fails.
    """
    saved = []
    try:
        for offset, (photo, thumb) in enumerate(processed):
            keys = storage.save(f"listings/{listing.id}", photo), storage.save(f"listings/{listing.id}", thumb)
            saved += keys
            listing.photos.append(ListingPhoto(position=first_position + offset, photo_key=keys[0], thumb_key=keys[1]))
    except Exception:
        for key in saved:
            storage.delete(key)
        raise
    return saved


def _process(data):
    try:
        return process_photo(data)
    except PhotoError as e:
        raise ListingError(e.code)


def _own_listing(s, user_id, listing_id):
    listing = s.get(Listing, listing_id)
    if listing is None or (listing.user_id != user_id and listing.status not in VISIBLE):
        raise ListingError("not_found", 404)
    if listing.user_id != user_id:
        raise ListingError("not_yours", 403)
    return listing
