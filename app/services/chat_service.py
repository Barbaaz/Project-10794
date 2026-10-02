"""
Marketplace conversations between a buyer and a seller (one per listing and buyer), with
the purchase steps (deal_status) in the same conversation:

    none ─request→ requested ─accept→ accepted ─sent→ sent ─received→ completed
                       │  └decline→ declined          │  └problem→ problem ─received→ completed
                       └cancel→ cancelled ←cancel─────┘ (before it's sent)

- accepting reserves the listing; cancelling an accepted purchase puts it back on sale;
- completed = the buyer confirmed it arrived, or SENT_AUTO_COMPLETE_DAYS after "sent" without
  a problem reported; the listing is then sold and other open requests for it are declined.
Each step also adds a message from the site (sender NULL, `event`), so both see the history.
"""
from app.services.photo_storage import storage
from db import connection, fetch_all, fetch_one

MAX_MESSAGE = 2000
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

CONVERSATION_COLUMNS = """
    c.id, c.listing_id, c.buyer_id, c.seller_id, c.deal_status, c.sent_at, c.completed_at,
    c.last_message_at, c.created_at, c.buyer_read_at, c.seller_read_at,
    l.price, l.status AS listing_status, l.condition, g.title, p.name AS platform_name,
    (SELECT TOP 1 thumb_key FROM listing_photos lp WHERE lp.listing_id = l.id ORDER BY lp.position) AS thumb_key,
    b.username AS buyer_username, b.display_name AS buyer_name,
    s.username AS seller_username, s.display_name AS seller_name
"""
CONVERSATION_JOINS = """
    FROM conversations c
    JOIN user_listings l ON l.id = c.listing_id
    JOIN games g ON g.id = l.game_id
    JOIN platforms p ON p.id = g.platform_id
    JOIN users b ON b.id = c.buyer_id
    JOIN users s ON s.id = c.seller_id
"""


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
    listing = fetch_one("SELECT id, user_id, status FROM user_listings WHERE id = ?", listing_id)
    if not listing or listing["status"] == "removed":
        raise ChatError("not_found", 404)
    if listing["user_id"] == user_id:
        raise ChatError("own_listing")

    existing = fetch_one("SELECT id FROM conversations WHERE listing_id = ? AND buyer_id = ?", listing_id, user_id)
    if existing:
        conversation_id = existing["id"]
    else:
        if listing["status"] != "active":
            raise ChatError("listing_unavailable")       # reserved / sold: no new conversations
        with connection() as conn:
            conversation_id = conn.cursor().execute(
                "INSERT INTO conversations (listing_id, buyer_id, seller_id) OUTPUT INSERTED.id VALUES (?, ?, ?)",
                listing_id, user_id, listing["user_id"],
            ).fetchone()[0]

    if message:
        send_message(user_id, conversation_id, message)
    if buy:
        deal_step(user_id, conversation_id, "request")
    return conversation_id


def send_message(user_id, conversation_id, body):
    conversation = _participant(user_id, conversation_id)
    body = (body or "").strip()
    if not body:
        raise ChatError("message_empty")
    if len(body) > MAX_MESSAGE:
        raise ChatError("message_long")
    with connection() as conn:
        _add_message(conn.cursor(), conversation, sender_id=user_id, body=body)
    return get_conversation(user_id, conversation_id)


def deal_step(user_id, conversation_id, action):
    """Move the purchase one step (see STEPS / CANCEL_FROM); its effects on the listing included."""
    conversation = _participant(user_id, conversation_id)
    role = _role(conversation, user_id)
    if action not in available_steps(conversation, role):
        raise ChatError("step_not_allowed", 409)
    status = "cancelled" if action == "cancel" else STEPS[action][2]

    with connection() as conn:
        cursor = conn.cursor()
        listing_status = cursor.execute(
            "SELECT status FROM user_listings WITH (UPDLOCK) WHERE id = ?", conversation["listing_id"]).fetchone()[0]
        if action in ("request", "accept") and listing_status != "active":
            raise ChatError("listing_unavailable", 409)

        cursor.execute(
            "UPDATE conversations SET deal_status = ?, "
            "sent_at = CASE WHEN ? = 'sent' THEN SYSUTCDATETIME() ELSE sent_at END WHERE id = ?",
            status, status, conversation_id,
        )
        if action == "accept":
            _set_listing(cursor, conversation["listing_id"], "reserved")
        elif action == "cancel" and conversation["deal_status"] == "accepted" and listing_status == "reserved":
            _set_listing(cursor, conversation["listing_id"], "active")
        _add_message(cursor, conversation, sender_id=None, event=action, actor_id=user_id)
        if status == "completed":
            _complete(cursor, conversation)
    return get_conversation(user_id, conversation_id)


def available_steps(conversation, role):
    """The purchase steps this side can take now (for the buttons)."""
    status = conversation["deal_status"]
    steps = [a for a, (who, from_, _) in STEPS.items() if who == role and status in from_]
    if status in CANCEL_FROM[role]:
        steps.append("cancel")
    # a reserved / sold listing takes no new requests, and can't be promised to a second buyer
    if conversation.get("listing_status", "active") != "active":
        steps = [s for s in steps if s not in ("request", "accept")]
    return steps


def complete_overdue():
    """Purchases sent SENT_AUTO_COMPLETE_DAYS ago without a problem reported: completed."""
    overdue = fetch_all(
        "SELECT id, listing_id, buyer_id, seller_id FROM conversations "
        "WHERE deal_status = 'sent' AND sent_at < DATEADD(DAY, ?, SYSUTCDATETIME())",
        -SENT_AUTO_COMPLETE_DAYS,
    )
    for conversation in overdue:
        with connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE conversations SET deal_status = 'completed' WHERE id = ? AND deal_status = 'sent'",
                           conversation["id"])
            if cursor.rowcount:
                _add_message(cursor, conversation, sender_id=None, event="auto_completed")
                _complete(cursor, conversation)
    return len(overdue)


def list_conversations(user_id):
    """The user's conversations, latest first, each with its unread count and the other side."""
    complete_overdue()
    rows = fetch_all(
        f"""
        SELECT {CONVERSATION_COLUMNS},
               (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id
                AND (m.sender_id IS NULL OR m.sender_id <> ?)
                AND m.created_at > COALESCE(CASE WHEN c.buyer_id = ? THEN c.buyer_read_at ELSE c.seller_read_at END,
                                            '1900-01-01')) AS unread,
               (SELECT TOP 1 COALESCE(m.body, '') FROM messages m WHERE m.conversation_id = c.id
                ORDER BY m.id DESC) AS last_body,
               (SELECT TOP 1 m.event FROM messages m WHERE m.conversation_id = c.id ORDER BY m.id DESC) AS last_event
        {CONVERSATION_JOINS}
        WHERE c.buyer_id = ? OR c.seller_id = ?
        ORDER BY c.last_message_at DESC
        """,
        user_id, user_id, user_id, user_id,
    )
    return [_for_user(r, user_id) for r in rows]


def unread_count(user_id):
    return sum(c["unread"] for c in list_conversations(user_id))


def get_conversation(user_id, conversation_id, after_id=0):
    """The conversation and its messages (only those after `after_id`, for refreshing); marks it read."""
    _participant(user_id, conversation_id)
    complete_overdue()
    conversation = fetch_one(f"SELECT {CONVERSATION_COLUMNS} {CONVERSATION_JOINS} WHERE c.id = ?", conversation_id)
    messages = fetch_all(
        "SELECT id, sender_id, body, event, created_at FROM messages WHERE conversation_id = ? AND id > ? ORDER BY id",
        conversation_id, int(after_id or 0),
    )
    read_column = "buyer_read_at" if conversation["buyer_id"] == user_id else "seller_read_at"
    with connection() as conn:
        conn.cursor().execute(f"UPDATE conversations SET {read_column} = SYSUTCDATETIME() WHERE id = ?", conversation_id)
    result = _for_user(conversation, user_id)
    result["messages"] = messages
    return result


# --- helpers ------------------------------------------------------------------------------

def _participant(user_id, conversation_id):
    conversation = fetch_one(
        "SELECT c.*, l.status AS listing_status FROM conversations c JOIN user_listings l ON l.id = c.listing_id "
        "WHERE c.id = ?", conversation_id)
    if not conversation or user_id not in (conversation["buyer_id"], conversation["seller_id"]):
        raise ChatError("not_found", 404)    # someone else's conversation: as if it didn't exist
    return conversation


def _role(conversation, user_id):
    return "buyer" if conversation["buyer_id"] == user_id else "seller"


def _add_message(cursor, conversation, sender_id, body=None, event=None, actor_id=None):
    """A message (or a site message about a step); the one who acted has read it already."""
    cursor.execute("INSERT INTO messages (conversation_id, sender_id, body, event) VALUES (?, ?, ?, ?)",
                   conversation["id"], sender_id, body, event)
    reader = sender_id or actor_id
    read_column = None if reader is None else "buyer_read_at" if reader == conversation["buyer_id"] else "seller_read_at"
    cursor.execute(
        "UPDATE conversations SET last_message_at = SYSUTCDATETIME()"
        + (f", {read_column} = SYSUTCDATETIME()" if read_column else "") + " WHERE id = ?",
        conversation["id"],
    )


def _set_listing(cursor, listing_id, status):
    cursor.execute(
        "UPDATE user_listings SET status = ?, updated_at = SYSUTCDATETIME(), "
        "sold_at = CASE WHEN ? = 'sold' THEN SYSUTCDATETIME() ELSE sold_at END WHERE id = ?",
        status, status, listing_id,
    )


def _complete(cursor, conversation):
    """A completed purchase: the listing is sold; other open requests for it are declined."""
    cursor.execute("UPDATE conversations SET completed_at = SYSUTCDATETIME() WHERE id = ?", conversation["id"])
    _set_listing(cursor, conversation["listing_id"], "sold")
    others = cursor.execute(
        "SELECT id, buyer_id, seller_id FROM conversations WHERE listing_id = ? AND id <> ? AND deal_status = 'requested'",
        conversation["listing_id"], conversation["id"],
    ).fetchall()
    for other_id, buyer_id, seller_id in others:
        cursor.execute("UPDATE conversations SET deal_status = 'declined' WHERE id = ?", other_id)
        _add_message(cursor, {"id": other_id, "buyer_id": buyer_id, "seller_id": seller_id},
                     sender_id=None, event="listing_sold")


def _for_user(row, user_id):
    """What one side sees: its role, the other side, the steps it can take, the thumbnail URL."""
    role = _role(row, user_id)
    other = "seller" if role == "buyer" else "buyer"
    row["role"] = role
    row["other_username"] = row[f"{other}_username"]
    row["other_name"] = row[f"{other}_name"]
    row["thumb_url"] = storage.url(row["thumb_key"]) if row.get("thumb_key") else None
    row["steps"] = available_steps(row, role)
    for column in ("buyer_read_at", "seller_read_at", "thumb_key"):
        row.pop(column, None)
    return row
