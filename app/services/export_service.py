"""
A user's own data as one JSON file (GDPR: right of access and portability): the account, listings,
conversations with their messages, ratings given and received, game reviews, the collection and
wishlist, reports they made and, for staff, their moderation actions. Never the password hash, and
nothing that names who reported them. Photos are listed by address (listing photos are public,
chat photos open for the two sides while logged in).
"""
from sqlalchemy import or_, select

from app.models import (
    CollectionItem, Conversation, GameReview, Listing, Message, ModerationLog, Rating, Report, User, fields,
)
from app.services.chat_service import message_dicts
from app.services.photo_storage import storage
from db import session

ACCOUNT_FIELDS = ("id", "username", "display_name", "email", "location", "role", "lang", "collection_public",
                  "wish_alerts", "created_at", "last_login_at")


def _game(game, edition=None):
    """How a game is named in the file: its title, platform and edition."""
    return {"game_id": game.id, "game": game.title, "platform": game.platform.name,
            "edition": edition.name if edition else None}


def _name(user):
    """The other person in a conversation or rating: their username (None once they deleted the account)."""
    return user.username if user else None


def export_user(user_id):
    """Everything the site keeps about this user, JSON-ready; None for an unknown or blocked account."""
    with session() as s:
        user = s.scalars(select(User).where(User.id == user_id, User.is_active)).first()
        if user is None:
            return None
        users = lambda ids: {u.id: u for u in s.scalars(select(User).where(User.id.in_(ids)))} if ids else {}

        listings = [fields(l, "id", "price", "condition", "description", "status", "created_at", "updated_at",
                           "sold_at", **_game(l.game, l.edition), photos=[storage.url(p.photo_key) for p in l.photos])
                    for l in s.scalars(select(Listing).where(Listing.user_id == user_id).order_by(Listing.id))]

        conversations = []
        for c in s.scalars(select(Conversation).where(or_(Conversation.buyer_id == user_id,
                                                          Conversation.seller_id == user_id)).order_by(Conversation.id)):
            mine = c.buyer_id == user_id
            messages = s.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.id)).all()
            names = users({m.sender_id for m in messages if m.sender_id})
            conversations.append(fields(
                c, "id", "deal_status", "sent_at", "completed_at", "created_at",
                role="buyer" if mine else "seller", other_user=_name(c.seller if mine else c.buyer),
                listing_id=c.listing_id, **_game(c.listing.game, c.listing.edition),
                messages=[{**m, "sender": "me" if m["sender_id"] == user_id
                           else _name(names.get(m["sender_id"])) if m["sender_id"] else "site"}
                          for m in message_dicts(c.id, messages)]))

        ratings = lambda column, other: [
            fields(r, "id", "conversation_id", "stars", "comment", "reply", "hidden", "created_at", "updated_at",
                   **{other: _name(s.get(User, r.rated_id if other == "rated" else r.rater_id))})
            for r in s.scalars(select(Rating).where(column == user_id).order_by(Rating.id))]

        collection = [fields(i, "id", "kind", "format", "status", "hours", "achievements", "achievements_total",
                             "notes", "wish_price", "created_at", "updated_at", **_game(i.game, i.edition))
                      for i in s.scalars(select(CollectionItem).where(CollectionItem.user_id == user_id)
                                         .order_by(CollectionItem.id))]

        reviews = [fields(r, "id", "score", "title", "body", "hidden", "created_at", "updated_at", **_game(r.game))
                   for r in s.scalars(select(GameReview).where(GameReview.user_id == user_id).order_by(GameReview.id))]

        reports = [fields(r, "id", "kind", "target_id", "reason", "details", "status", "created_at", "resolved_at",
                          "resolution")
                   for r in s.scalars(select(Report).where(Report.reporter_id == user_id).order_by(Report.id))]

        moderation = [fields(m, "id", "action", "kind", "target_id", "note", "created_at")
                      for m in s.scalars(select(ModerationLog).where(ModerationLog.moderator_id == user_id)
                                         .order_by(ModerationLog.id))]

        return {
            "account": fields(user, *ACCOUNT_FIELDS),
            "listings": listings,
            "conversations": conversations,
            "ratings_given": ratings(Rating.rater_id, "rated"),
            "ratings_received": ratings(Rating.rated_id, "rater"),
            "game_reviews": reviews,
            "collection": collection,
            "reports_made": reports,
            "moderation_actions": moderation,
        }
