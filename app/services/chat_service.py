"""
Marketplace conversations between a buyer and a seller (one per listing and buyer), with
the purchase steps (deal_status) in the same conversation:

    none ─request→ requested ─accept→ accepted ─sent→ sent ─received→ completed
                       │  └decline→ declined          │  └problem→ problem ─received→ completed
                       └cancel→ cancelled ←cancel─────┘ (before it's sent)

- accepting reserves the listing; cancelling an accepted purchase puts it back on sale;
- completed = the buyer confirmed it arrived, or SENT_AUTO_COMPLETE_DAYS after "sent" without
  a problem reported; the listing is then sold and other open requests for it are declined.
Each step also adds a message from the site (sender None, `event`), so both see the history.
A message can carry photos (more pictures of the copy when the buyer asks, a damaged parcel):
private to the conversation, served by photo_file() to its two sides and to moderators.
"""
from datetime import datetime, timedelta

from sqlalchemy import case, func, or_, select

from app.models import NOW, Conversation, Listing, Message, MessagePhoto, fields
from app.services.photo_storage import PhotoError, process_photo, storage
from app.services.rating_service import check_not_blocked, ratings_of_conversation
from db import session

MAX_MESSAGE = 2000
MAX_MESSAGE_PHOTOS = 5
SENT_AUTO_COMPLETE_DAYS = 7

# action → (who may do it, from which statuses, to which status)
STEPS = {
    "request":  ("buyer",  {"none", "declined", "cancelled"}, "requested"),
    "accept":   ("seller", {"requested"}, "accepted"),
    "decline":  ("seller", {"requested"}, "declined"),
    "sent":     ("seller", {"accepted"}, "sent"),
    "received": ("buyer",  {"sent", "problem"}, "completed"),
    "problem":  ("buyer",  {"sent"}, "problem"),
}
# Cancelling: the buyer until it's sent, the seller once accepted (a request is declined instead)
CANCEL_FROM = {"buyer": {"requested", "accepted"}, "seller": {"accepted"}}


class ChatError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def start(user_id, listing_id, message=None, buy=False):
    """
    The buyer opens (or reopens) the conversation about a listing, optionally with a first
    message and / or a purchase request (the Buy button). Returns the conversation id.
    """
    with session() as s:
        listing = s.get(Listing, listing_id)
        if not listing or listing.status == "removed":
            raise ChatError("not_found", 404)
        if listing.user_id == user_id:
            raise ChatError("own_listing")
        conversation = s.scalars(select(Conversation).where(Conversation.listing_id == listing_id,
                                                            Conversation.buyer_id == user_id)).first()
        if not conversation:
            if listing.status != "active":
                raise ChatError("listing_unavailable")       # reserved / sold: no new conversations
            conversation = Conversation(listing_id=listing_id, buyer_id=user_id, seller_id=listing.user_id)
            s.add(conversation)
            s.flush()
        conversation_id = conversation.id

    if message:
        send_message(user_id, conversation_id, message)
    if buy:
        deal_step(user_id, conversation_id, "request")
    return conversation_id


def send_message(user_id, conversation_id, body, photos=()):
    """A message: text, photos (the uploaded files' bytes, up to MAX_MESSAGE_PHOTOS), or both."""
    body = (body or "").strip()
    with session() as s:
        _participant(s, user_id, conversation_id)
    if not body and not photos:
        raise ChatError("message_empty")
    if len(body) > MAX_MESSAGE:
        raise ChatError("message_long")
    if len(photos) > MAX_MESSAGE_PHOTOS:
        raise ChatError("message_photos_many")
    try:
        processed = [process_photo(data) for data in photos]    # all checked before any is kept
    except PhotoError as e:
        raise ChatError(e.code)

    keys = []
    try:
        with session() as s:
            conversation = _participant(s, user_id, conversation_id)
            message = _add_message(s, conversation, sender_id=user_id, body=body or None)
            for position, (photo, thumb) in enumerate(processed):
                keys += [storage.save(f"chats/{conversation_id}", photo), storage.save(f"chats/{conversation_id}", thumb)]
                s.add(MessagePhoto(message_id=message.id, position=position, photo_key=keys[-2], thumb_key=keys[-1]))
    except Exception:
        for key in keys:            # nothing saved in the database: no files left behind either
            storage.delete(key)
        raise
    return get_conversation(user_id, conversation_id)


def photo_file(user_id, conversation_id, photo_id, thumb=False, staff=False):
    """The storage key of a photo sent in a conversation, for its two sides (or a moderator: staff=True)."""
    with session() as s:
        if not staff:
            _participant(s, user_id, conversation_id)
        photo = s.scalars(select(MessagePhoto).join(Message).where(
            MessagePhoto.id == photo_id, Message.conversation_id == conversation_id)).first()
        if not photo:
            raise ChatError("not_found", 404)
        return photo.thumb_key if thumb else photo.photo_key


def message_dicts(conversation_id, messages):
    """Messages as the pages get them, with their photos' addresses (thumbnail and full size)."""
    url = f"/api/conversations/{conversation_id}/photos/"
    return [fields(m, "id", "sender_id", "body", "event", "created_at",
                   photos=[{"id": p.id, "thumb_url": f"{url}{p.id}?thumb=1", "url": f"{url}{p.id}"} for p in m.photos])
            for m in messages]


def deal_step(user_id, conversation_id, action):
    """Move the purchase one step (see STEPS / CANCEL_FROM); its effects on the listing included."""
    with session() as s:
        conversation = _participant(s, user_id, conversation_id)
        role = _role(conversation, user_id)
        if action not in available_steps(conversation.deal_status, role, conversation.listing.status):
            raise ChatError("step_not_allowed", 409)
        if action == "request":
            check_not_blocked(user_id, ChatError)      # a rating overdue: rate first
        status = "cancelled" if action == "cancel" else STEPS[action][2]

        # locked until the end: two buyers can't both get the same copy
        listing = s.get(Listing, conversation.listing_id, with_for_update={"of": Listing}, populate_existing=True)
        if action in ("request", "accept") and listing.status != "active":
            raise ChatError("listing_unavailable", 409)

        previous = conversation.deal_status
        conversation.deal_status = status
        if status == "sent":
            conversation.sent_at = NOW
        if action == "accept":
            _set_listing(listing, "reserved")
        elif action == "cancel" and previous == "accepted" and listing.status == "reserved":
            _set_listing(listing, "active")
        _add_message(s, conversation, sender_id=None, event=action, actor_id=user_id)
        if status == "completed":
            _complete(s, conversation, listing)
    return get_conversation(user_id, conversation_id)


def available_steps(deal_status, role, listing_status="active"):
    """The purchase steps this side can take now (for the buttons)."""
    steps = [a for a, (who, from_, _) in STEPS.items() if who == role and deal_status in from_]
    if deal_status in CANCEL_FROM[role]:
        steps.append("cancel")
    # a reserved / sold listing takes no new requests, and can't be promised to a second buyer
    if listing_status != "active":
        steps = [s for s in steps if s not in ("request", "accept")]
    return steps


def complete_overdue():
    """Purchases sent SENT_AUTO_COMPLETE_DAYS ago without a problem reported: completed."""
    with session() as s:
        overdue = s.scalars(select(Conversation.id).where(
            Conversation.deal_status == "sent",
            Conversation.sent_at < NOW - timedelta(days=SENT_AUTO_COMPLETE_DAYS))).all()
    for conversation_id in overdue:
        with session() as s:
            conversation = s.get(Conversation, conversation_id, with_for_update={"of": Conversation})
            if conversation.deal_status != "sent":       # completed meanwhile by the buyer
                continue
            conversation.deal_status = "completed"
            _add_message(s, conversation, sender_id=None, event="auto_completed")
            _complete(s, conversation, s.get(Listing, conversation.listing_id))
    return len(overdue)


def list_conversations(user_id):
    """The user's conversations, latest first, each with its unread count and last message."""
    complete_overdue()
    with session() as s:
        conversations = s.scalars(
            select(Conversation).where(or_(Conversation.buyer_id == user_id, Conversation.seller_id == user_id))
            .order_by(Conversation.last_message_at.desc())).unique().all()
        ids = [c.id for c in conversations]
        if not ids:
            return []
        # unread: messages from the other side (or the site) after this user last read it
        my_read_at = case((Conversation.buyer_id == user_id, Conversation.buyer_read_at), else_=Conversation.seller_read_at)
        unread = dict(s.execute(
            select(Message.conversation_id, func.count())
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Message.conversation_id.in_(ids),
                   or_(Message.sender_id.is_(None), Message.sender_id != user_id),
                   Message.created_at > func.coalesce(my_read_at, datetime(1900, 1, 1)))
            .group_by(Message.conversation_id)).all())
        ranked = select(Message.id, Message.conversation_id, Message.body, Message.event,
                        func.row_number().over(partition_by=Message.conversation_id,
                                               order_by=Message.id.desc()).label("rn")
                        ).where(Message.conversation_id.in_(ids)).subquery()
        last = {r.conversation_id: r for r in s.execute(select(ranked).where(ranked.c.rn == 1))}
        with_photos = set(s.scalars(select(MessagePhoto.message_id).where(
            MessagePhoto.message_id.in_([r.id for r in last.values()]))))
        return [{**_as_dict(c, user_id), "unread": unread.get(c.id, 0),
                 "last_body": last[c.id].body or "" if c.id in last else None,
                 "last_event": last[c.id].event if c.id in last else None,
                 "last_photos": c.id in last and last[c.id].id in with_photos}
                for c in conversations]


def unread_count(user_id):
    return sum(c["unread"] for c in list_conversations(user_id))


def get_conversation(user_id, conversation_id, after_id=0):
    """The conversation and its messages (only those after `after_id`, for refreshing); marks it read."""
    with session() as s:
        _participant(s, user_id, conversation_id)
    complete_overdue()
    with session() as s:
        conversation = s.get(Conversation, conversation_id)
        new = s.scalars(select(Message).where(Message.conversation_id == conversation_id, Message.id > int(after_id or 0))
                        .order_by(Message.id)).all()
        messages = message_dicts(conversation_id, new)
        result = _as_dict(conversation, user_id)
        # read up to the newest message returned, not "now": one being saved meanwhile (an earlier time,
        # committed later) stays unread. A poll with nothing new writes nothing
        newest = max((m.created_at for m in new), default=None)
        read_at = conversation.buyer_read_at if conversation.buyer_id == user_id else conversation.seller_read_at
        if newest is not None and (read_at is None or newest > read_at):
            _mark_read(conversation, user_id, up_to=newest)
    result["messages"] = messages
    if result["deal_status"] == "completed":
        result["ratings"] = ratings_of_conversation(user_id, conversation_id)
    return result


# --- helpers ------------------------------------------------------------------------------

def _participant(s, user_id, conversation_id):
    conversation = s.get(Conversation, conversation_id)
    if not conversation or user_id not in (conversation.buyer_id, conversation.seller_id):
        raise ChatError("not_found", 404)    # someone else's conversation: as if it didn't exist
    return conversation


def _role(conversation, user_id):
    return "buyer" if conversation.buyer_id == user_id else "seller"


def _mark_read(conversation, user_id, up_to=NOW):
    """This side has read the conversation up to `up_to` (the newest message seen; now for one's own)."""
    if conversation.buyer_id == user_id:
        conversation.buyer_read_at = up_to
    else:
        conversation.seller_read_at = up_to


def _add_message(s, conversation, sender_id, body=None, event=None, actor_id=None):
    """
    A message (or a site message about a step); the one who acted has read it already.
    The message is saved first, so the read mark set after it is later than the message.
    """
    message = Message(conversation_id=conversation.id, sender_id=sender_id, body=body, event=event)
    s.add(message)
    s.flush()
    conversation.last_message_at = NOW
    reader = sender_id or actor_id
    if reader is not None:
        _mark_read(conversation, reader)
    s.flush()
    return message


def _set_listing(listing, status):
    listing.status, listing.updated_at = status, NOW
    if status == "sold":
        listing.sold_at = NOW


def _complete(s, conversation, listing):
    """A completed purchase: the listing is sold; other open requests for it are declined."""
    conversation.completed_at = NOW
    _set_listing(listing, "sold")
    others = s.scalars(select(Conversation).where(Conversation.listing_id == conversation.listing_id,
                                                  Conversation.id != conversation.id,
                                                  Conversation.deal_status == "requested")).all()
    for other in others:
        other.deal_status = "declined"
        _add_message(s, other, sender_id=None, event="listing_sold")


def _as_dict(c, user_id):
    """What one side sees: the conversation, the listing, the other side, the steps it can take."""
    role = _role(c, user_id)
    other = c.seller if role == "buyer" else c.buyer
    listing = c.listing
    thumb = listing.photos[0].thumb_key if listing.photos else None
    return fields(
        c, "id", "listing_id", "buyer_id", "seller_id", "deal_status", "sent_at", "completed_at",
        "last_message_at", "created_at",
        price=fields(listing, "price")["price"], listing_status=listing.status, condition=listing.condition,
        title=listing.game.title, platform_name=listing.game.platform.name,
        buyer_username=c.buyer.username, buyer_name=c.buyer.display_name,
        seller_username=c.seller.username, seller_name=c.seller.display_name,
        role=role, other_username=other.username, other_name=other.display_name,
        thumb_url=storage.url(thumb) if thumb else None,
        steps=available_steps(c.deal_status, role, listing.status),
    )
