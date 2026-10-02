"""
Ratings between marketplace users. After a completed purchase each side must rate the other
(1–5 stars, optional comment): pending ratings are reminded on every page, and one left
OVERDUE_DAYS after the purchase completed blocks new purchases and listings until it's given
(user decision 2026-10-02: not blocked right away, people buy several games at once).
A rating can be changed for EDIT_DAYS; the rated user may reply to it.
"""
from datetime import timedelta

from sqlalchemy import Numeric, and_, cast, exists, func, literal_column, or_, select

from app.models import NOW, Conversation, Rating, User, fields
from db import session

OVERDUE_DAYS = 14
EDIT_DAYS = 14
MAX_TEXT = 500
DAY = literal_column("DAY")    # DATEADD's first argument is a keyword, not a value


class RatingError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def _unrated(user_id):
    """Completed purchases of this user without their rating (a condition on Conversation)."""
    return and_(
        Conversation.deal_status == "completed",
        or_(Conversation.buyer_id == user_id, Conversation.seller_id == user_id),
        ~exists().where(Rating.conversation_id == Conversation.id, Rating.rater_id == user_id),
    )


def _now(s):
    return s.scalar(select(NOW))      # the database's clock (UTC), as the stored times


def rate(user_id, conversation_id, stars, comment=None):
    """Rate the other side of a completed purchase (or change one's rating within EDIT_DAYS)."""
    with session() as s:
        conversation = s.get(Conversation, conversation_id)
        if not conversation or user_id not in (conversation.buyer_id, conversation.seller_id):
            raise RatingError("not_found", 404)
        if conversation.deal_status != "completed":
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

        rating = s.scalars(select(Rating).where(Rating.conversation_id == conversation_id,
                                                Rating.rater_id == user_id)).first()
        if rating:
            if _now(s) - rating.created_at > timedelta(days=EDIT_DAYS):
                raise RatingError("rating_locked", 409)
            rating.stars, rating.comment, rating.updated_at = stars, comment, NOW
        else:
            rated_id = conversation.seller_id if user_id == conversation.buyer_id else conversation.buyer_id
            s.add(Rating(conversation_id=conversation_id, rater_id=user_id, rated_id=rated_id,
                         stars=stars, comment=comment))
    return ratings_of_conversation(user_id, conversation_id)


def reply(user_id, rating_id, text):
    """The rated user answers a rating (shown under it); can be changed, or emptied."""
    text = (text or "").strip() or None
    if text and len(text) > MAX_TEXT:
        raise RatingError("comment_long")
    with session() as s:
        rating = s.get(Rating, rating_id)
        if not rating or rating.rated_id != user_id:
            raise RatingError("not_found", 404)
        rating.reply = text
        return fields(rating, "id", "stars", "comment", "reply")


def ratings_of_conversation(user_id, conversation_id):
    """{mine, theirs}: the two ratings of a purchase, as one side sees them (None if not given)."""
    with session() as s:
        now = _now(s)
        ratings = [
            fields(r, "id", "rater_id", "stars", "comment", "reply", "created_at", "hidden",
                   editable=now - r.created_at <= timedelta(days=EDIT_DAYS))
            for r in s.scalars(select(Rating).where(Rating.conversation_id == conversation_id))
        ]
    return {"mine": next((r for r in ratings if r["rater_id"] == user_id), None),
            "theirs": next((r for r in ratings if r["rater_id"] != user_id), None)}


def pending(user_id):
    """The completed purchases this user still has to rate, oldest first; `overdue` ones block."""
    with session() as s:
        now = _now(s)
        conversations = s.scalars(select(Conversation).where(_unrated(user_id))
                                  .order_by(Conversation.completed_at)).all()
        return [{
            "conversation_id": c.id,
            "completed_at": fields(c, "completed_at")["completed_at"],
            "title": c.listing.game.title,
            "other_username": (c.seller if c.buyer_id == user_id else c.buyer).username,
            "overdue": c.completed_at < now - timedelta(days=OVERDUE_DAYS),
        } for c in conversations]


def check_not_blocked(user_id, error_class):
    """Raise error_class("ratings_overdue", 403) when a rating is OVERDUE_DAYS late (no new purchases / listings)."""
    with session() as s:
        late = s.scalar(select(func.count()).select_from(Conversation).where(
            _unrated(user_id), Conversation.completed_at < func.dateadd(DAY, -OVERDUE_DAYS, NOW)))
    if late:
        raise error_class("ratings_overdue", 403)


def summaries(user_ids):
    """
    {user_id: (average stars to one decimal, number of ratings)} for these users (rated ones only);
    ratings hidden by a moderator don't count.
    """
    if not user_ids:
        return {}
    average = cast(func.avg(cast(Rating.stars, Numeric(3, 2))), Numeric(3, 1))
    with session() as s:
        rows = s.execute(select(Rating.rated_id, average, func.count())
                         .where(Rating.rated_id.in_(set(user_ids)), ~Rating.hidden).group_by(Rating.rated_id)).all()
    return {user_id: (float(avg), count) for user_id, avg, count in rows}


def profile(username):
    """A user's public page: name, member since, rating, the ratings they got, their active listings."""
    from app.services.listing_service import listings_of_user   # listing_service imports this module
    with session() as s:
        user = s.scalars(select(User).where(User.username == username, User.is_active)).first()
        if not user:
            return None
        result = fields(user, "id", "username", "display_name", "created_at")
        ratings = s.scalars(select(Rating).where(Rating.rated_id == user.id, ~Rating.hidden)
                            .order_by(Rating.created_at.desc())).all()
        result["ratings"] = [
            fields(r, "id", "stars", "comment", "reply", "created_at",
                   rater_username=r.rater.username,
                   rated_as="seller" if r.conversation.seller_id == r.rated_id else "buyer",
                   title=r.conversation.listing.game.title)
            for r in ratings
        ]
    rating, count = summaries([result["id"]]).get(result["id"], (None, 0))
    result.update(rating=rating, rating_count=count, listings=listings_of_user(result["id"]))
    return result

