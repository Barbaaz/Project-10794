"""
The pre-owned marketplace: games people sell (user_listings) with their photos.
Only the seller changes a listing. A listing always has MIN_PHOTOS..MAX_PHOTOS photos.
"""
from decimal import Decimal, InvalidOperation

from app.services.photo_storage import PhotoError, process_photo, storage
from app.services.common import EDITION_CARD_COLUMNS, card_group, page_result
from app.services.rating_service import check_not_blocked, rating_columns
from db import connection, fetch_all, fetch_one, placeholders

CONDITIONS = ("new", "like_new", "good", "fair", "poor")
STATUSES = ("active", "reserved", "sold", "removed")
VISIBLE = ("active", "reserved")      # shown to everyone; sold / removed only to the seller
MIN_PHOTOS, MAX_PHOTOS = 3, 10
MIN_PRICE, MAX_PRICE = Decimal("0.50"), Decimal("10000")
MAX_DESCRIPTION = 2000

# A listing as everyone sees it (with the seller's rating): never the seller's email
LISTING_COLUMNS = f"""
    l.id, l.user_id, l.game_id, l.edition_id, l.price, l.condition, l.description, l.status,
    l.created_at, l.updated_at, l.sold_at,
    g.title, p.code AS platform, p.name AS platform_name, e.name AS edition,
    u.username AS seller_username, u.display_name AS seller_name, u.created_at AS seller_since,
    {rating_columns("l.user_id", "seller_")}
"""
LISTING_JOINS = """
    FROM user_listings l
    JOIN games g ON g.id = l.game_id
    JOIN platforms p ON p.id = g.platform_id
    JOIN users u ON u.id = l.user_id
    LEFT JOIN game_editions e ON e.id = l.edition_id
"""


class ListingError(Exception):
    """A problem the seller can fix; `code` is translated by the page."""

    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def create_listing(user_id, game_id, edition_id, price, condition, description, photos):
    """photos: the uploaded files' bytes. Returns the new listing."""
    check_not_blocked(user_id, ListingError)       # a rating overdue: rate first
    fields = _checked_fields(price, condition, description)
    game_id, edition_id = _checked_game(game_id, edition_id)
    if not MIN_PHOTOS <= len(photos) <= MAX_PHOTOS:
        raise ListingError("photo_count")
    processed = [_process(data) for data in photos]   # all checked before anything is saved

    with connection() as conn:
        cursor = conn.cursor()
        listing_id = cursor.execute(
            "INSERT INTO user_listings (user_id, game_id, edition_id, price, condition, description) "
            "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?)",
            user_id, game_id, edition_id, fields["price"], fields["condition"], fields["description"],
        ).fetchone()[0]
        _save_photos(cursor, listing_id, processed, first_position=0)
    return get_listing(listing_id, viewer_id=user_id)


def listings_for_game(game_id):
    """The game's listings everyone can see (active first, cheapest first), each with its photos."""
    rows = fetch_all(
        f"SELECT {LISTING_COLUMNS} {LISTING_JOINS} WHERE l.game_id = ? AND l.status IN ('active', 'reserved') "
        "ORDER BY CASE l.status WHEN 'active' THEN 0 ELSE 1 END, l.price",
        game_id,
    )
    return _with_photos(rows)


BROWSE_SORTS = {
    "newest": "u.newest DESC, g.title",
    "price_asc": "u.min_price, g.title",
    "price_desc": "u.min_price DESC, g.title",
}


def browse(platform=None, sort="newest", page=1, per_page=48):
    """
    The market tab: one group per game edition users sell (a game can have several sellers),
    each with its active listings, cheapest first; editions with the newest listing first, or
    by their cheapest price. Paged by edition.
    """
    used = """
        WITH u AS (
            SELECT edition_id, MIN(price) AS min_price, MAX(created_at) AS newest
            FROM user_listings WHERE status = 'active' AND edition_id IS NOT NULL GROUP BY edition_id
        )"""
    joins = """
        FROM u JOIN game_editions e ON e.id = u.edition_id
        JOIN games g ON g.id = e.game_id JOIN platforms p ON p.id = g.platform_id
        WHERE (? IS NULL OR p.code = ?)"""
    total = fetch_one(f"{used} SELECT COUNT(*) AS total {joins}", platform, platform)["total"]
    editions = fetch_all(
        f"{used} SELECT {EDITION_CARD_COLUMNS}, g.image_url AS image {joins} "
        f"ORDER BY {BROWSE_SORTS.get(sort, BROWSE_SORTS['newest'])} OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        platform, platform, (page - 1) * per_page, per_page,
    )
    ids = [e["edition_id"] for e in editions]
    listings = _with_photos(fetch_all(
        f"SELECT {LISTING_COLUMNS} {LISTING_JOINS} WHERE l.status = 'active' AND l.edition_id IN ({placeholders(ids)}) "
        "ORDER BY l.price, l.created_at", *ids)) if ids else []
    groups = [card_group(e, [], image=e["image"], listings=[l for l in listings if l["edition_id"] == e["edition_id"]])
              for e in editions]
    return page_result(page, per_page, total, groups=groups)


def used_summaries(edition_ids):
    """
    {edition_id: {count, price, listing_id}}: the active listings of these editions, for the
    "Used" button on catalogue cards: how many, the lowest price and that listing.
    """
    if not edition_ids:
        return {}
    rows = fetch_all(
        f"""
        SELECT edition_id, COUNT(*) OVER (PARTITION BY edition_id) AS count, price, id AS listing_id,
               ROW_NUMBER() OVER (PARTITION BY edition_id ORDER BY price, id) AS rn
        FROM user_listings
        WHERE status = 'active' AND edition_id IN ({placeholders(edition_ids)})
        """,
        *edition_ids,
    )
    return {r["edition_id"]: {"count": r["count"], "price": r["price"], "listing_id": r["listing_id"]}
            for r in rows if r["rn"] == 1}


def listings_of_user(user_id):
    """A seller's listings everyone can see (their profile page), newest first."""
    rows = fetch_all(
        f"SELECT {LISTING_COLUMNS} {LISTING_JOINS} WHERE l.user_id = ? AND l.status IN ('active', 'reserved') "
        "ORDER BY l.created_at DESC",
        user_id,
    )
    return _with_photos(rows)


def my_listings(user_id):
    """The seller's own listings (all but removed), newest first."""
    rows = fetch_all(
        f"SELECT {LISTING_COLUMNS} {LISTING_JOINS} WHERE l.user_id = ? AND l.status <> 'removed' "
        "ORDER BY l.created_at DESC",
        user_id,
    )
    return _with_photos(rows)


def get_listing(listing_id, viewer_id=None):
    """
    A listing with its photos, or None if this viewer can't see it: sold / removed listings are
    only shown to their seller and to the people who talked to the seller about them (a buyer
    can still see what they bought).
    """
    row = fetch_one(f"SELECT {LISTING_COLUMNS} {LISTING_JOINS} WHERE l.id = ?", listing_id)
    if not row:
        return None
    if row["status"] not in VISIBLE and row["user_id"] != viewer_id and not (viewer_id and fetch_one(
            "SELECT 1 AS ok FROM conversations WHERE listing_id = ? AND buyer_id = ?", listing_id, viewer_id)):
        return None
    return _with_photos([row])[0]


def update_listing(user_id, listing_id, changes):
    """The seller changes price / condition / description / status."""
    listing = _own_listing(user_id, listing_id)
    fields = _checked_fields(
        changes.get("price", listing["price"]),
        changes.get("condition", listing["condition"]),
        changes.get("description", listing["description"]),
    )
    status = changes.get("status", listing["status"])
    if status not in STATUSES:
        raise ListingError("status_invalid")
    with connection() as conn:
        conn.cursor().execute(
            "UPDATE user_listings SET price = ?, condition = ?, description = ?, status = ?, "
            "sold_at = CASE WHEN ? = 'sold' THEN COALESCE(sold_at, SYSUTCDATETIME()) END, "
            "updated_at = SYSUTCDATETIME() WHERE id = ?",
            fields["price"], fields["condition"], fields["description"], status, status, listing_id,
        )
    return get_listing(listing_id, viewer_id=user_id)


def add_photos(user_id, listing_id, photos):
    listing = _own_listing(user_id, listing_id)
    if len(listing["photos"]) + len(photos) > MAX_PHOTOS:
        raise ListingError("photo_count")
    processed = [_process(data) for data in photos]
    with connection() as conn:
        position = max((p["position"] for p in listing["photos"]), default=-1) + 1
        _save_photos(conn.cursor(), listing_id, processed, first_position=position)
    return get_listing(listing_id, viewer_id=user_id)


def delete_photo(user_id, listing_id, photo_id):
    listing = _own_listing(user_id, listing_id)
    photo = next((p for p in listing["photos"] if p["id"] == photo_id), None)
    if photo is None:
        raise ListingError("not_found", 404)
    if len(listing["photos"]) <= MIN_PHOTOS:
        raise ListingError("photo_count")
    with connection() as conn:
        conn.cursor().execute("DELETE FROM listing_photos WHERE id = ?", photo_id)
    storage.delete(photo["photo_key"])
    storage.delete(photo["thumb_key"])
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
    if not fetch_one("SELECT 1 AS ok FROM games WHERE id = ?", game_id):
        raise ListingError("game_invalid")
    if edition_id is not None and not fetch_one(
            "SELECT 1 AS ok FROM game_editions WHERE id = ? AND game_id = ?", edition_id, game_id):
        raise ListingError("edition_invalid")
    return game_id, edition_id


def _save_photos(cursor, listing_id, processed, first_position):
    """
    Store the processed photos' files and add their rows (in the caller's transaction).
    If anything fails, the files stored so far are deleted again: no files without a row.
    """
    saved = []
    try:
        for offset, (photo, thumb) in enumerate(processed):
            keys = storage.save(f"listings/{listing_id}", photo), storage.save(f"listings/{listing_id}", thumb)
            saved += keys
            cursor.execute("INSERT INTO listing_photos (listing_id, position, photo_key, thumb_key) VALUES (?, ?, ?, ?)",
                           listing_id, first_position + offset, *keys)
    except Exception:
        for key in saved:
            storage.delete(key)
        raise


def _process(data):
    try:
        return process_photo(data)
    except PhotoError as e:
        raise ListingError(e.code)


def _own_listing(user_id, listing_id):
    listing = get_listing(listing_id, viewer_id=user_id)
    if listing is None:
        raise ListingError("not_found", 404)
    if listing["user_id"] != user_id:
        raise ListingError("not_yours", 403)
    return listing


def _with_photos(rows):
    if not rows:
        return rows
    ids = [r["id"] for r in rows]
    photos = fetch_all(
        f"SELECT id, listing_id, position, photo_key, thumb_key FROM listing_photos "
        f"WHERE listing_id IN ({placeholders(ids)}) ORDER BY listing_id, position",
        *ids,
    )
    for row in rows:
        row["photos"] = [
            {**p, "url": storage.url(p["photo_key"]), "thumb_url": storage.url(p["thumb_key"])}
            for p in photos if p["listing_id"] == row["id"]
        ]
    return rows
