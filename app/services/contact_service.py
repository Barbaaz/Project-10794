"""
The Contactos page (user, 2026-10-16): anyone writes to the site's team (a question, a problem, a store to
add, a suggestion). Kept in contact_messages and read by moderators / admins in /admin, where they're
marked handled; also e-mailed to ALERT_EMAIL once e-mail works (until then only logged). Replies go by
e-mail, from the team's own mailbox, to the address given.
Against spam: a field people don't see (bots fill it in: thanked, not kept) and at most MAX_PER_HOUR
messages from one address an hour.
"""
import logging
import threading
import time

from sqlalchemy import select

from app import config
from app.models import CONTACT_TOPICS, NOW, ContactMessage, User
from app.services import mail_service
from app.services.auth_service import EMAIL
from db import session

log = logging.getLogger(__name__)

MAX_NAME, MAX_EMAIL, MIN_BODY, MAX_BODY = 100, 255, 10, 4000
MAX_PER_HOUR = 5
MAX_LISTED = 200
MAX_TRACKED = 10000
_sent, _sent_lock = {}, threading.Lock()


class ContactError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def _too_many(ip):
    """Whether this address sent MAX_PER_HOUR messages in the last hour; else counts this one. Bounded memory."""
    now = time.monotonic()
    with _sent_lock:
        recent = [t for t in _sent.get(ip, []) if now - t < 3600]
        if len(recent) >= MAX_PER_HOUR:
            _sent[ip] = recent
            return True
        if ip not in _sent and len(_sent) >= MAX_TRACKED:
            _sent.pop(next(iter(_sent)))
        _sent[ip] = recent + [now]
    return False


def send(data, user_id=None, ip="?"):
    """{name, email, topic, body, website (the hidden field)} → {ok}. A logged-in user's message is linked
    to their account (the team sees who wrote)."""
    name = " ".join(str(data.get("name") or "").split())
    email = str(data.get("email") or "").strip().lower()
    topic = data.get("topic")
    body = str(data.get("body") or "").strip()
    if not 1 <= len(name) <= MAX_NAME:
        raise ContactError("contact_name_invalid")
    if not EMAIL.match(email) or len(email) > MAX_EMAIL:
        raise ContactError("email_invalid")
    if topic not in CONTACT_TOPICS:
        raise ContactError("contact_topic_invalid")
    if len(body) < MIN_BODY:
        raise ContactError("contact_body_short")
    if len(body) > MAX_BODY:
        raise ContactError("contact_body_long")
    if data.get("website"):                      # only a bot sees that field
        log.info("Contact form: hidden field filled in, from %s; not kept", ip)
        return {"ok": True}
    if _too_many(ip):
        raise ContactError("contact_too_many", 429)
    with session() as s:
        message = ContactMessage(user_id=user_id, name=name, email=email, topic=topic, body=body)
        s.add(message)
        s.flush()
        message_id = message.id
        username = s.scalar(select(User.username).where(User.id == user_id)) if user_id else None
    if config.ALERT_EMAIL:
        who = f"{name} <{email}>" + (f" (@{username})" if username else "")
        try:
            mail_service.send(config.ALERT_EMAIL, f"SaveOnGames: contacto ({topic}) de {name}",
                              f"De: {who}\nAssunto: {topic}\n\n{body}\n\n{config.SITE_URL}/admin#contact (n.º {message_id})\n"
                              f"Responder para: {email}\n")
        except Exception as e:           # kept anyway: the team sees it in /admin
            log.warning("Contact message %s not e-mailed: %s", message_id, e)
    return {"ok": True}


def messages(handled=False):
    """The messages, newest first, for /admin: open ones (handled=False) or handled ones."""
    with session() as s:
        writer, handler = User.__table__.alias("writer"), User.__table__.alias("handler")
        rows = s.execute(
            select(ContactMessage, writer.c.username, handler.c.username)
            .outerjoin(writer, writer.c.id == ContactMessage.user_id)
            .outerjoin(handler, handler.c.id == ContactMessage.handled_by)
            .where(ContactMessage.handled_at.is_not(None) if handled else ContactMessage.handled_at.is_(None))
            .order_by(ContactMessage.id.desc()).limit(MAX_LISTED)).all()
        return [{"id": m.id, "name": m.name, "email": m.email, "topic": m.topic, "body": m.body, "created_at": m.created_at,
                 "username": username, "handled_at": m.handled_at, "handled_by": handled_by}
                for m, username, handled_by in rows]


def open_count():
    with session() as s:
        return len(s.scalars(select(ContactMessage.id).where(ContactMessage.handled_at.is_(None))).all())


def mark(message_id, handled, moderator_id):
    """Mark a message handled (or open again)."""
    with session() as s:
        message = s.get(ContactMessage, message_id)
        if not message:
            raise ContactError("not_found", 404)
        message.handled_at, message.handled_by = (NOW, moderator_id) if handled else (None, None)
    return {"ok": True}
