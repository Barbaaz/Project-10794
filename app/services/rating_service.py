"""
Ratings between marketplace users. After a completed purchase each side must rate the other
(1–5 stars, optional comment): pending ratings are reminded on every page, and one left
OVERDUE_DAYS after the purchase completed blocks new purchases and listings until it's given
(user decision 2026-10-02: not blocked right away, people buy several games at once).
A rating can be changed for EDIT_DAYS; the rated user may reply to it.
"""
from db import connection, fetch_all, fetch_one

OVERDUE_DAYS = 14
EDIT_DAYS = 14
MAX_TEXT = 500


class RatingError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


# A completed purchase this user hasn't rated yet (c = conversations)
UNRATED = """
    c.deal_status = 'completed' AND (c.buyer_id = ? OR c.seller_id = ?)
    AND NOT EXISTS (SELECT 1 FROM user_ratings r WHERE r.conversation_id = c.id AND r.rater_id = ?)
"""


def rate(user_id, conversation_id, stars, comment=None):
    """Rate the other side of a completed purchase (or change one's rating within EDIT_DAYS)."""
    conversation = fetch_one("SELECT id, buyer_id, seller_id, deal_status FROM conversations WHERE id = ?",
                             conversation_id)
    if not conversation or user_id not in (conversation["buyer_id"], conversation["seller_id"]):
        raise RatingError("not_found", 404)
    if conversation["deal_status"] != "completed":
        raise RatingError("not_completed", 409)
    try:
        stars = int(stars)
    except (TypeError, ValueError):
        raise RatingError("stars_invalid")
    if not 1 <= stars <= 5:
        raise RatingError("stars_invalid")
    comment = (comment or "").strip() or None
    if comment and len(comment) > MAX_TEXT:
        raise RatingError("comment_long")

    rated_id = conversation["seller_id"] if user_id == conversation["buyer_id"] else conversation["buyer_id"]
    existing = fetch_one(
        "SELECT id, DATEDIFF(DAY, created_at, SYSUTCDATETIME()) AS age FROM user_ratings "
        "WHERE conversation_id = ? AND rater_id = ?", conversation_id, user_id)
    with connection() as conn:
        if existing:
            if existing["age"] > EDIT_DAYS:
                raise RatingError("rating_locked", 409)
            conn.cursor().execute(
                "UPDATE user_ratings SET stars = ?, comment = ?, updated_at = SYSUTCDATETIME() WHERE id = ?",
                stars, comment, existing["id"])
        else:
            conn.cursor().execute(
                "INSERT INTO user_ratings (conversation_id, rater_id, rated_id, stars, comment) VALUES (?, ?, ?, ?, ?)",
                conversation_id, user_id, rated_id, stars, comment)
    return ratings_of_conversation(user_id, conversation_id)


def reply(user_id, rating_id, text):
    """The rated user answers a rating (shown under it); can be changed, or emptied."""
    rating = fetch_one("SELECT id, rated_id FROM user_ratings WHERE id = ?", rating_id)
    if not rating or rating["rated_id"] != user_id:
        raise RatingError("not_found", 404)
    text = (text or "").strip() or None
    if text and len(text) > MAX_TEXT:
        raise RatingError("comment_long")
    with connection() as conn:
        conn.cursor().execute("UPDATE user_ratings SET reply = ? WHERE id = ?", text, rating_id)
    return fetch_one("SELECT id, stars, comment, reply FROM user_ratings WHERE id = ?", rating_id)


def ratings_of_conversation(user_id, conversation_id):
    """{mine, theirs}: the two ratings of a purchase, as one side sees them (None if not given)."""
    rows = fetch_all(
        "SELECT id, rater_id, stars, comment, reply, created_at, "
        "CAST(CASE WHEN DATEDIFF(DAY, created_at, SYSUTCDATETIME()) <= ? THEN 1 ELSE 0 END AS BIT) AS editable "
        "FROM user_ratings WHERE conversation_id = ?", EDIT_DAYS, conversation_id)
    return {"mine": next((r for r in rows if r["rater_id"] == user_id), None),
            "theirs": next((r for r in rows if r["rater_id"] != user_id), None)}


def pending(user_id):
    """The completed purchases this user still has to rate, oldest first; `overdue` ones block."""
    return fetch_all(
        f"""
        SELECT c.id AS conversation_id, c.completed_at, g.title,
               CASE WHEN c.buyer_id = ? THEN s.username ELSE b.username END AS other_username,
               CAST(CASE WHEN c.completed_at < DATEADD(DAY, ?, SYSUTCDATETIME()) THEN 1 ELSE 0 END AS BIT) AS overdue
        FROM conversations c
        JOIN user_listings l ON l.id = c.listing_id JOIN games g ON g.id = l.game_id
        JOIN users b ON b.id = c.buyer_id JOIN users s ON s.id = c.seller_id
        WHERE {UNRATED}
        ORDER BY c.completed_at
        """,
        user_id, -OVERDUE_DAYS, user_id, user_id, user_id,
    )


def check_not_blocked(user_id, error_class):
    """Raise error_class("ratings_overdue", 403) when a rating is OVERDUE_DAYS late (no new purchases / listings)."""
    late = fetch_one(
        f"SELECT COUNT(*) AS n FROM conversations c WHERE {UNRATED} "
        "AND c.completed_at < DATEADD(DAY, ?, SYSUTCDATETIME())",
        user_id, user_id, user_id, -OVERDUE_DAYS,
    )["n"]
    if late:
        raise error_class("ratings_overdue", 403)


def rating_columns(user_column, prefix=""):
    """
    SQL columns with a user's average stars and number of ratings, to add to a SELECT:
    rating_columns("l.user_id", "seller_") → seller_rating, seller_rating_count.
    """
    ratings = f"FROM user_ratings r WHERE r.rated_id = {user_column}"
    return (f"(SELECT CAST(AVG(CAST(r.stars AS DECIMAL(3,2))) AS DECIMAL(3,1)) {ratings}) AS {prefix}rating, "
            f"(SELECT COUNT(*) {ratings}) AS {prefix}rating_count")


def profile(username):
    """A user's public page: name, member since, rating, the ratings they got, their active listings."""
    user = fetch_one(
        "SELECT id, username, display_name, created_at FROM users WHERE username = ? AND is_active = 1", username)
    if not user:
        return None
    user.update(fetch_one(f"SELECT {rating_columns('u.id')} FROM users u WHERE u.id = ?", user["id"]))
    user["ratings"] = fetch_all(
        """
        SELECT r.id, r.stars, r.comment, r.reply, r.created_at, u.username AS rater_username,
               CASE WHEN c.seller_id = r.rated_id THEN 'seller' ELSE 'buyer' END AS rated_as, g.title
        FROM user_ratings r
        JOIN users u ON u.id = r.rater_id
        JOIN conversations c ON c.id = r.conversation_id
        JOIN user_listings l ON l.id = c.listing_id JOIN games g ON g.id = l.game_id
        WHERE r.rated_id = ?
        ORDER BY r.created_at DESC
        """,
        user["id"],
    )
    from app.services.listing_service import listings_of_user   # listing_service imports this module
    user["listings"] = listings_of_user(user["id"])
    return user
