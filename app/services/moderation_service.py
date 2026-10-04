"""
Moderation. Logged-in users report a listing, a user, a rating or a game review; moderators
(role moderator or admin) see the open reports and act: hide / restore a listing (the seller
can't undo a hide), hide / restore a rating or a review (a hidden one isn't shown or counted;
its writer can't change or delete it), block / unblock a user
(logged out, can't log in, their listings disappear), or dismiss the report. Every action is
written to the moderation log. Admins also name and remove moderators; admins themselves are
only made from the command line (python -m database.users role …).
"""
from datetime import timedelta

from sqlalchemy import func, select

from app.models import (
    NOW, REPORT_KINDS, REPORT_REASONS, Conversation, GameReview, Listing, ModerationLog, Rating, Report, User,
    fields,
)
from db import session

MAX_REPORTS_PER_DAY = 20
MAX_DETAILS = 1000
MAX_NOTE = 500

# action → (kind of thing it applies to, what it does)
ACTIONS = {
    "hide_listing": "listing", "restore_listing": "listing",
    "hide_rating": "rating", "restore_rating": "rating",
    "hide_review": "review", "restore_review": "review",
    "block_user": "user", "unblock_user": "user",
    "dismiss": None,
}


class ModerationError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


# --- reporting (any logged-in user) ------------------------------------------------------

def report(user_id, kind, target_id, reason, details=None):
    if kind not in REPORT_KINDS:
        raise ModerationError("report_kind_invalid")
    if reason not in REPORT_REASONS:
        raise ModerationError("report_reason_invalid")
    details = (details or "").strip() or None
    if details and len(details) > MAX_DETAILS:
        raise ModerationError("details_long")
    try:
        target_id = int(target_id)
    except (TypeError, ValueError):
        raise ModerationError("not_found", 404)

    with session() as s:
        owner = _owner_of(s, kind, target_id)
        if owner is None:
            raise ModerationError("not_found", 404)
        if owner == user_id:
            raise ModerationError("report_own")              # yourself / your own listing, rating or review
        already = s.scalar(select(Report.id).where(Report.reporter_id == user_id, Report.kind == kind,
                                                   Report.target_id == target_id, Report.status == "open").limit(1))
        if already:
            raise ModerationError("report_duplicate", 409)
        today = s.scalar(select(func.count()).select_from(Report).where(
            Report.reporter_id == user_id, Report.created_at > s.scalar(select(NOW)) - timedelta(days=1)))
        if today >= MAX_REPORTS_PER_DAY:
            raise ModerationError("report_limit", 429)
        s.add(Report(reporter_id=user_id, kind=kind, target_id=target_id, reason=reason, details=details))
    return {"ok": True}


def _owner_of(s, kind, target_id):
    """Whose this thing is (the user id), or None if it doesn't exist (for reports)."""
    if kind == "listing":
        listing = s.get(Listing, target_id)
        return listing.user_id if listing and listing.status != "removed" else None
    if kind == "user":
        user = s.get(User, target_id)
        return user.id if user and user.is_active else None
    if kind == "review":
        review = s.get(GameReview, target_id)
        return review.user_id if review else None
    rating = s.get(Rating, target_id)
    return rating.rater_id if rating else None          # a rating is its writer's


# --- for moderators ----------------------------------------------------------------------

def open_reports():
    """Open reports, grouped by the thing reported (most reported first), each with a summary of it."""
    with session() as s:
        reports = s.scalars(select(Report).where(Report.status == "open").order_by(Report.created_at)).all()
        groups = {}
        for r in reports:
            group = groups.setdefault((r.kind, r.target_id), {
                "kind": r.kind, "target_id": r.target_id, "target": _summary(s, r.kind, r.target_id), "reports": []})
            group["reports"].append(fields(r, "id", "reason", "details", "created_at", reporter=r.reporter.username))
        return sorted(groups.values(), key=lambda g: -len(g["reports"]))


def _summary(s, kind, target_id):
    """What a moderator needs to see about a reported thing."""
    if kind == "listing":
        l = s.get(Listing, target_id)
        return l and fields(l, "id", "price", "status", "description", "removed_by_moderator",
                            title=l.game.title, platform=l.game.platform.name, seller=l.seller.username)
    if kind == "user":
        u = s.get(User, target_id)
        return u and fields(u, "id", "username", "display_name", "role", "is_active", "created_at")
    if kind == "review":
        r = s.get(GameReview, target_id)
        return r and fields(r, "id", "game_id", "score", "title", "body", "hidden", writer=r.user.username,
                            game=r.game.title, platform=r.game.platform.name)
    r = s.get(Rating, target_id)
    return r and fields(r, "id", "stars", "comment", "reply", "hidden", rater=r.rater.username,
                        rated=s.get(User, r.rated_id).username, title=r.conversation.listing.game.title)


def act(moderator_id, action, target_id, note=None):
    """A moderator's action on a thing; resolves its open reports (or dismisses them) and logs it."""
    if action not in ACTIONS:
        raise ModerationError("action_invalid")
    note = (note or "").strip() or None
    if note and len(note) > MAX_NOTE:
        raise ModerationError("details_long")

    with session() as s:
        moderator = s.get(User, moderator_id)
        kind = ACTIONS[action]
        if action == "dismiss":
            report = s.get(Report, target_id)            # dismiss: the target is a report
            if not report or report.status != "open":
                raise ModerationError("not_found", 404)
            kind, target_id = report.kind, report.target_id
        else:
            _apply(s, moderator, action, target_id)

        status = "dismissed" if action == "dismiss" else "resolved"
        for report in s.scalars(select(Report).where(Report.kind == kind, Report.target_id == target_id,
                                                     Report.status == "open")):
            report.status, report.resolved_by, report.resolved_at, report.resolution = status, moderator_id, NOW, note
        s.add(ModerationLog(moderator_id=moderator_id, action=action, kind=kind, target_id=target_id, note=note))
    return {"ok": True}


def _apply(s, moderator, action, target_id):
    if action in ("hide_listing", "restore_listing"):
        listing = s.get(Listing, target_id)
        if not listing:
            raise ModerationError("not_found", 404)
        hide = action == "hide_listing"
        listing.removed_by_moderator = hide
        listing.status = "removed" if hide else "sold" if listing.sold_at else "active"
        listing.updated_at = NOW
    elif action in ("hide_rating", "restore_rating"):
        rating = s.get(Rating, target_id)
        if not rating:
            raise ModerationError("not_found", 404)
        rating.hidden = action == "hide_rating"
    elif action in ("hide_review", "restore_review"):
        review = s.get(GameReview, target_id)
        if not review:
            raise ModerationError("not_found", 404)
        review.hidden = action == "hide_review"
    else:
        user = s.get(User, target_id)
        if not user:
            raise ModerationError("not_found", 404)
        # admins can't be blocked here; only an admin blocks a moderator; nobody blocks themselves
        if user.id == moderator.id or user.role == "admin" or (user.role == "moderator" and moderator.role != "admin"):
            raise ModerationError("not_allowed", 403)
        user.is_active = action == "unblock_user"


def problem_purchases():
    """Purchases where the buyer reported a problem: for a moderator to look at."""
    with session() as s:
        conversations = s.scalars(select(Conversation).where(Conversation.deal_status == "problem")
                                  .order_by(Conversation.last_message_at.desc())).all()
        return [fields(c, "id", "sent_at", "last_message_at", title=c.listing.game.title,
                       price=fields(c.listing, "price")["price"], buyer=c.buyer.username, seller=c.seller.username)
                for c in conversations]


def conversation_messages(conversation_id):
    """A conversation's messages, read-only, for a moderator looking into a problem or a report."""
    from app.models import Message
    from app.services.chat_service import message_dicts
    with session() as s:
        conversation = s.get(Conversation, conversation_id)
        if not conversation:
            raise ModerationError("not_found", 404)
        return {
            "buyer": conversation.buyer.username, "seller": conversation.seller.username,
            "buyer_id": conversation.buyer_id, "title": conversation.listing.game.title,
            "deal_status": conversation.deal_status,
            "messages": message_dicts(conversation_id, s.scalars(
                select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id))),
        }


def log(limit=100):
    with session() as s:
        return [fields(entry, "id", "action", "kind", "target_id", "note", "created_at",
                       moderator=entry.moderator.username)
                for entry in s.scalars(select(ModerationLog).order_by(ModerationLog.id.desc()).limit(limit))]


# --- for admins --------------------------------------------------------------------------

def staff():
    """The moderators and admins."""
    with session() as s:
        return [fields(u, "id", "username", "role") for u in
                s.scalars(select(User).where(User.role != "user").order_by(User.role, User.username))]


def set_role(admin_id, username, role):
    """An admin names (or removes) a moderator. Admins are only made from the command line."""
    if role not in ("user", "moderator"):
        raise ModerationError("role_invalid")
    with session() as s:
        user = s.scalars(select(User).where(User.named(username))).first()
        if not user:
            raise ModerationError("not_found", 404)
        if user.role == "admin":
            raise ModerationError("not_allowed", 403)
        user.role = role
        s.add(ModerationLog(moderator_id=admin_id, action=f"role_{role}", kind="user", target_id=user.id))
    return staff()
