"""
Accounts: sign up with a username, email and password; log in with the username or the email.
Passwords are hashed (werkzeug's scrypt), never stored as typed; a forgotten one is replaced
through a signed link sent by e-mail (no table: the link names the user and expires; see
request_password_reset). Google / Microsoft sign-in
come later and create accounts without a password (password_hash None).
"""
import hashlib
import hmac
import logging
import re
import threading
import time

from sqlalchemy import or_, select
from werkzeug.security import check_password_hash, generate_password_hash

from app import config
from app.models import NOW, User, fields
from app.services import mail_service
from db import session

log = logging.getLogger(__name__)

USERNAME = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8
MAX_PASSWORD = 200        # longer isn't a real password: refused before hashing it
MAX_LOGIN = 255           # a username or email (emails are at most 255)
LANGS = ("pt", "en")      # the page's languages; the user's is kept for e-mails (wishlist alerts)

# After this many wrong passwords for one login (username / email) from one address,
# that pair is locked for LOCK_SECONDS: slows down password guessing
MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60
MAX_SIGNUPS = 10         # sign-up tries from one address per SIGNUP_SECONDS (accounts made in bulk)
SIGNUP_SECONDS = 60 * 60
MAX_TRACKED = 10_000      # (ip, login) pairs remembered at most: stale ones go first, then the oldest
_failures = {}   # (ip, login) → [times of recent failures]
_failures_lock = threading.Lock()   # the server answers several requests at once

# What a user sees about their own account (never the password hash). Other people see less:
# never the email (see the marketplace's seller info)
OWN_FIELDS = ("id", "username", "display_name", "email", "location", "role", "created_at")


class AccountError(Exception):
    """A sign-up / log-in problem the person can fix; `code` is translated by the page."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def register(username, email, password, display_name=None, lang=None, ip=None):
    """A new account. ip: the visitor's address, for the sign-up limit (None from the command line: no limit)."""
    if ip is not None:
        key = (ip, "sign up")
        if _locked(key, MAX_SIGNUPS, SIGNUP_SECONDS):
            raise AccountError("register_locked")
        _note_failure(key)                 # every try counts (also those refused below)
    username, email = (username or "").strip(), (email or "").strip().lower()
    display_name = (display_name or "").strip() or username
    if not USERNAME.match(username):
        raise AccountError("username_invalid")
    if not EMAIL.match(email) or len(email) > 255:
        raise AccountError("email_invalid")
    _check_password(password)
    if len(display_name) > 100:
        raise AccountError("display_name_long")

    with session() as s:
        # usernames compare without case; emails are stored in lower case
        taken = s.scalars(select(User).where(or_(User.named(username), User.email == email))).first()
        if taken:
            raise AccountError("username_taken" if (taken.username or "").lower() == username.lower() else "email_taken")
        user = User(username=username, email=email, password_hash=generate_password_hash(password),
                    display_name=display_name, lang=lang if lang in LANGS else "pt")
        s.add(user)
        s.flush()
        user_id = user.id
    return get_user(user_id)


def authenticate(login, password, ip="?", lang=None):
    """The user for this username / email and password; AccountError("login_failed" / "login_locked")."""
    login = (login or "").strip()
    if len(login) > MAX_LOGIN or len(password or "") > MAX_PASSWORD:
        raise AccountError("login_failed")        # no such account: not looked up, hashed or remembered
    key = (ip, login.lower())
    if _locked(key):
        raise AccountError("login_locked")

    with session() as s:
        user = s.scalars(select(User).where(or_(User.named(login), User.email == login.lower()))).first()
        # check a hash even when there's no such user, so the answer takes as long either way
        hash_ = user.password_hash if user and user.password_hash else _DUMMY_HASH
        if not (check_password_hash(hash_, password or "") and user and user.password_hash and user.is_active):
            _note_failure(key)
            raise AccountError("login_failed")
        user.last_login_at = NOW
        if lang in LANGS:
            user.lang = lang
        user_id = user.id

    with _failures_lock:
        _failures.pop(key, None)
    return get_user(user_id)


# --- forgotten password: a link by e-mail ---------------------------------------------------
RESET_SECONDS = 60 * 60
RESET_MAIL = {
    "pt": ("Nova palavra-passe",
           "Olá {username},\n\nPara escolher uma nova palavra-passe, abra esta ligação (válida durante 1 hora):\n"
           "{link}\n\nSe não foi o próprio a pedir, ignore este email: a palavra-passe fica como está."),
    "en": ("New password",
           "Hello {username},\n\nTo choose a new password, open this link (it works for 1 hour):\n"
           "{link}\n\nIf you didn't ask for this, ignore this email: your password stays as it is."),
}


def _reset_tokens():
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(config.SECRET_KEY, salt="password-reset")


def _password_mark(user):
    """Part of the reset link: once the password changes, links made before stop working (each works once)."""
    return hashlib.sha256((user.password_hash or "").encode()).hexdigest()[:16]


def request_password_reset(email, lang="pt", ip="?"):
    """
    E-mail a link to choose a new password. Nothing tells whether the address has an account
    (the same answer either way). At most MAX_FAILURES requests per address (IP) per LOCK_SECONDS.
    """
    key = (ip, "password reset")
    if _locked(key):
        raise AccountError("reset_locked")
    _note_failure(key)

    email = (email or "").strip().lower()
    with session() as s:
        user = s.scalars(select(User).where(User.email == email, User.is_active)).first()
        if not user:
            return
        token = _reset_tokens().dumps({"id": user.id, "mark": _password_mark(user)})
        username = user.username
    subject, text = RESET_MAIL.get(lang, RESET_MAIL["pt"])
    # in the background: sending takes seconds, and only for real accounts, so waiting for it would tell
    in_background(mail_service.send, email, subject,
                  text.format(username=username, link=f"{config.SITE_URL}/account?reset={token}"))


def in_background(work, *args):
    """Run work(*args) in its own thread; a failure is logged (the person sees the same answer either way)."""
    def run():
        try:
            work(*args)
        except Exception:
            log.exception("Background work failed: %s", getattr(work, "__name__", work))
    threading.Thread(target=run, daemon=True).start()


def reset_password(token, password):
    """A new password from a reset link (logged in afterwards); AccountError("reset_invalid") for an old or used link."""
    _check_password(password)
    from itsdangerous import BadSignature
    try:
        data = _reset_tokens().loads(token or "", max_age=RESET_SECONDS)
    except BadSignature:            # also an expired one
        raise AccountError("reset_invalid")

    with session() as s:
        user = s.get(User, data.get("id"))
        if not user or not user.is_active or _password_mark(user) != data.get("mark"):
            raise AccountError("reset_invalid")
        user.password_hash = generate_password_hash(password)
        user_id, logins = user.id, {user.username.lower(), user.email}
    with _failures_lock:
        for key in [k for k in _failures if k[1] in logins]:      # locked out by wrong passwords: not any more
            _failures.pop(key, None)
    return get_user(user_id)


def get_user(user_id, mark=None):
    """
    The user's own account fields, or None (also for a blocked account). With `mark` (a login
    cookie's session_mark): None too when the password changed since that login, so a new
    password logs out every other copy of the cookie.
    """
    if user_id is None:
        return None
    with session() as s:
        user = s.scalars(select(User).where(User.id == user_id, User.is_active)).first()
        if not user or (mark is not None and not hmac.compare_digest(str(mark), _session_mark(user))):
            return None
        return fields(user, *OWN_FIELDS)


def session_mark(user_id):
    """What the login cookie keeps besides the user id (see get_user)."""
    with session() as s:
        user = s.get(User, user_id)
        return _session_mark(user) if user else None


def _session_mark(user):
    """Changes when the password does. Keyed with the secret key: the cookie is signed, not hidden,
    so it mustn't tell anything about the password hash."""
    return hmac.new(config.SECRET_KEY.encode(), b"session:" + (user.password_hash or "").encode(),
                    hashlib.sha256).hexdigest()[:32]


def _check_password(password):
    if len(password or "") < MIN_PASSWORD:
        raise AccountError("password_short")
    if len(password) > MAX_PASSWORD:
        raise AccountError("password_long")


def _locked(key, limit=MAX_FAILURES, seconds=LOCK_SECONDS):
    """Whether this (ip, login) has `limit` failures in the last `seconds`; forgets older ones (and keeps
    no record for a key without any, or every login tried would stay in memory)."""
    now = time.monotonic()
    with _failures_lock:
        recent = [t for t in _failures.get(key, []) if now - t < seconds]
        if recent:
            _failures[key] = recent
        else:
            _failures.pop(key, None)
    return len(recent) >= limit


def _note_failure(key):
    """Remember a failure for the lock-out. At most MAX_TRACKED keys: stale ones are dropped first,
    then the oldest (a bounded memory beats a perfect count under a flood of different logins)."""
    now = time.monotonic()
    with _failures_lock:
        if key not in _failures and len(_failures) >= MAX_TRACKED:
            for stale in [k for k, times in _failures.items() if now - times[-1] >= LOCK_SECONDS]:
                del _failures[stale]
            while len(_failures) >= MAX_TRACKED:
                del _failures[next(iter(_failures))]
        _failures.setdefault(key, []).append(now)


_DUMMY_HASH = generate_password_hash("not a real password")
