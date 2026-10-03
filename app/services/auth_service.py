"""
Accounts: sign up with a username, email and password; log in with the username or the email.
Passwords are hashed (werkzeug's scrypt), never stored as typed. Google / Microsoft sign-in
come later and create accounts without a password (password_hash None).
"""
import re
import time

from sqlalchemy import or_, select
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import NOW, User, fields
from db import session

USERNAME = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8

# After this many wrong passwords for one login (username / email) from one address,
# that pair is locked for LOCK_SECONDS: slows down password guessing
MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60
_failures = {}   # (ip, login) → [times of recent failures]

# What a user sees about their own account (never the password hash). Other people see less:
# never the email (see the marketplace's seller info)
OWN_FIELDS = ("id", "username", "display_name", "email", "location", "role", "created_at")


class AccountError(Exception):
    """A sign-up / log-in problem the person can fix; `code` is translated by the page."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def register(username, email, password, display_name=None):
    username, email = (username or "").strip(), (email or "").strip().lower()
    display_name = (display_name or "").strip() or username
    if not USERNAME.match(username):
        raise AccountError("username_invalid")
    if not EMAIL.match(email) or len(email) > 255:
        raise AccountError("email_invalid")
    if len(password or "") < MIN_PASSWORD:
        raise AccountError("password_short")
    if len(display_name) > 100:
        raise AccountError("display_name_long")

    with session() as s:
        # usernames compare without case; emails are stored in lower case
        taken = s.scalars(select(User).where(or_(User.named(username), User.email == email))).first()
        if taken:
            raise AccountError("username_taken" if (taken.username or "").lower() == username.lower() else "email_taken")
        user = User(username=username, email=email, password_hash=generate_password_hash(password),
                    display_name=display_name)
        s.add(user)
        s.flush()
        user_id = user.id
    return get_user(user_id)


def authenticate(login, password, ip="?"):
    """The user for this username / email and password; AccountError("login_failed" / "login_locked")."""
    login = (login or "").strip()
    key = (ip, login.lower())
    if _locked(key):
        raise AccountError("login_locked")

    with session() as s:
        user = s.scalars(select(User).where(or_(User.named(login), User.email == login.lower()))).first()
        # check a hash even when there's no such user, so the answer takes as long either way
        hash_ = user.password_hash if user and user.password_hash else _DUMMY_HASH
        if not (check_password_hash(hash_, password or "") and user and user.password_hash and user.is_active):
            _failures.setdefault(key, []).append(time.monotonic())
            raise AccountError("login_failed")
        user.last_login_at = NOW
        user_id = user.id

    _failures.pop(key, None)
    return get_user(user_id)


def get_user(user_id):
    """The user's own account fields, or None (also for a blocked account)."""
    if user_id is None:
        return None
    with session() as s:
        user = s.scalars(select(User).where(User.id == user_id, User.is_active)).first()
        return fields(user, *OWN_FIELDS) if user else None


def _locked(key):
    recent = [t for t in _failures.get(key, []) if time.monotonic() - t < LOCK_SECONDS]
    _failures[key] = recent
    return len(recent) >= MAX_FAILURES


_DUMMY_HASH = generate_password_hash("not a real password")
