"""
/api/auth: sign up, log in, a forgotten password, log out, who am I. The login is a signed session cookie
(HttpOnly, SameSite=Lax; see app/web.py), holding the user id and a mark of their password
(auth_service.session_mark): a new password logs out every other session.
"""
import json
from datetime import date
from functools import wraps

from flask import Blueprint, Response, abort, g, jsonify, request, session

from app.services import auth_service, export_service
from app.services.auth_service import AccountError

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def current_user():
    """The logged-in user (cached for the request), or None."""
    if "user" not in g:
        g.user = auth_service.get_user(session.get("user_id"), mark=session.get("mark", ""))
        if g.user is None:
            # deleted or blocked since logging in, or the password changed (another device, a stolen cookie)
            session.pop("user_id", None)
            session.pop("mark", None)
    return g.user


def login_required(view):
    """401 for API calls without a logged-in user."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            abort(401, description="login_required")
        return view(*args, **kwargs)
    return wrapper


def role_required(*roles):
    """401 without a logged-in user, 403 when their role isn't one of `roles`."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                abort(401, description="login_required")
            if user["role"] not in roles:
                abort(403, description="not_allowed")
            return view(*args, **kwargs)
        return wrapper
    return decorator


moderator_required = role_required("moderator", "admin")
admin_required = role_required("admin")


def log_in(user):
    session.clear()            # a new session on login (no reuse of one set before)
    session["user_id"] = user["id"]
    session["mark"] = auth_service.session_mark(user["id"])   # a new password ends this session
    session.permanent = True   # stays logged in (PERMANENT_SESSION_LIFETIME) instead of until the browser closes
    g.user = user


def account_error(e):
    return jsonify(error=e.code), 429 if e.code.endswith("_locked") else 400


@bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    try:
        user = auth_service.register(data.get("username"), data.get("email"), data.get("password"),
                                     data.get("display_name"), data.get("lang"), ip=request.remote_addr or "?")
    except AccountError as e:
        return account_error(e)
    log_in(user)
    return jsonify(user), 201


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    try:
        user = auth_service.authenticate(data.get("login"), data.get("password"), request.remote_addr or "?",
                                         data.get("lang"))
    except AccountError as e:
        return account_error(e)
    log_in(user)
    return jsonify(user)


@bp.post("/forgot")
def forgot():
    """{email, lang}: e-mail a link to choose a new password; the same answer whether or not it has an account."""
    data = request.get_json(silent=True) or {}
    try:
        auth_service.request_password_reset(data.get("email"), data.get("lang"), request.remote_addr or "?")
    except AccountError as e:
        return account_error(e)
    return jsonify(ok=True)


@bp.post("/reset")
def reset():
    """{token, password}: the new password from the e-mailed link; logged in afterwards."""
    data = request.get_json(silent=True) or {}
    try:
        user = auth_service.reset_password(data.get("token"), data.get("password"))
    except AccountError as e:
        return account_error(e)
    log_in(user)
    return jsonify(user)


@bp.post("/password")
@login_required
def change_password():
    """{current, password}: a new password; this session stays, every other one is logged out."""
    data = request.get_json(silent=True) or {}
    try:
        user = auth_service.change_password(current_user()["id"], data.get("current"), data.get("password"),
                                            request.remote_addr or "?")
    except AccountError as e:
        return account_error(e)
    log_in(user)                 # this session gets the new password's mark
    return jsonify(user)


@bp.post("/delete")
@login_required
def delete_account():
    """{password}: delete (anonymise) the account, then log out (auth_service.delete_account)."""
    data = request.get_json(silent=True) or {}
    try:
        auth_service.delete_account(current_user()["id"], data.get("password"), request.remote_addr or "?")
    except AccountError as e:
        return account_error(e)
    session.clear()
    return jsonify(ok=True)


@bp.get("/export")
@login_required
def export():
    """The user's own data as a JSON file to save (export_service)."""
    data = export_service.export_user(current_user()["id"])
    response = Response(json.dumps(data, ensure_ascii=False, indent=2), mimetype="application/json")
    response.headers["Content-Disposition"] = f'attachment; filename="project10794-{date.today()}.json"'
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/me")
def me():
    """The logged-in user, or null."""
    return jsonify(current_user())
