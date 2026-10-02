"""
Accounts: sign up with a username, email and password; log in with the username or the email.
Passwords are hashed (werkzeug's scrypt), never stored as typed. Google / Microsoft sign-in
come later and create accounts without a password (password_hash NULL).
"""
import re
import time

from werkzeug.security import check_password_hash, generate_password_hash

from db import connection, fetch_one

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
OWN_COLUMNS = "id, username, display_name, email, location, is_admin, created_at"


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

    with connection() as conn:
        cursor = conn.cursor()
        taken = cursor.execute(
            "SELECT CASE WHEN username = ? THEN 'username' ELSE 'email' END FROM users WHERE username = ? OR email = ?",
            username, username, email,
        ).fetchone()
        if taken:
            raise AccountError(f"{taken[0]}_taken")
        user_id = cursor.execute(
            "INSERT INTO users (username, email, password_hash, display_name) OUTPUT INSERTED.id VALUES (?, ?, ?, ?)",
            username, email, generate_password_hash(password), display_name,
        ).fetchone()[0]
    return get_user(user_id)


def authenticate(login, password, ip="?"):
    """The user for this username / email and password; AccountError("login_failed" / "login_locked")."""
    login = (login or "").strip()
    key = (ip, login.lower())
    if _locked(key):
        raise AccountError("login_locked")

    row = fetch_one(
        "SELECT id, password_hash, is_active FROM users WHERE username = ? OR email = ?", login, login.lower())
    # check a hash even when there's no such user, so the answer takes as long either way
    hash_ = row["password_hash"] if row and row["password_hash"] else _DUMMY_HASH
    if not (check_password_hash(hash_, password or "") and row and row["password_hash"] and row["is_active"]):
        _failures.setdefault(key, []).append(time.monotonic())
        raise AccountError("login_failed")

    _failures.pop(key, None)
    with connection() as conn:
        conn.cursor().execute("UPDATE users SET last_login_at = SYSUTCDATETIME() WHERE id = ?", row["id"])
    return get_user(row["id"])


def get_user(user_id):
    """The user's own account fields, or None (also for a blocked account)."""
    if user_id is None:
        return None
    return fetch_one(f"SELECT {OWN_COLUMNS} FROM users WHERE id = ? AND is_active = 1", user_id)


def _locked(key):
    recent = [t for t in _failures.get(key, []) if time.monotonic() - t < LOCK_SECONDS]
    _failures[key] = recent
    return len(recent) >= MAX_FAILURES


_DUMMY_HASH = generate_password_hash("not a real password")
