"""
/api/auth: sign up, log in, log out, who am I. The login is a signed session cookie
(HttpOnly, SameSite=Lax; see app/web.py), holding only the user id.
"""
from functools import wraps

from flask import Blueprint, abort, g, jsonify, request, session

from app.services import auth_service
from app.services.auth_service import AccountError

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def current_user():
    """The logged-in user (cached for the request), or None."""
    if "user" not in g:
        g.user = auth_service.get_user(session.get("user_id"))
        if g.user is None:
            session.pop("user_id", None)   # deleted or blocked since logging in
    return g.user


def login_required(view):
    """401 for API calls without a logged-in user."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            abort(401, description="login_required")
        return view(*args, **kwargs)
    return wrapper


def log_in(user):
    session.clear()            # a new session on login (no reuse of one set before)
    session["user_id"] = user["id"]
    session.permanent = True   # stays logged in (PERMANENT_SESSION_LIFETIME) instead of until the browser closes
    g.user = user


def account_error(e):
    return jsonify(error=e.code), 400 if e.code != "login_locked" else 429


@bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    try:
        user = auth_service.register(data.get("username"), data.get("email"), data.get("password"),
                                     data.get("display_name"))
    except AccountError as e:
        return account_error(e)
    log_in(user)
    return jsonify(user), 201


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    try:
        user = auth_service.authenticate(data.get("login"), data.get("password"), request.remote_addr or "?")
    except AccountError as e:
        return account_error(e)
    log_in(user)
    return jsonify(user)


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/me")
def me():
    """The logged-in user, or null."""
    return jsonify(current_user())
