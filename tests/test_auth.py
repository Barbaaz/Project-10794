"""Accounts: sign up, log in / out, lock-out, and the protection against requests from other sites."""
import psycopg
import pytest

from app.services import auth_service
from helpers import HEADERS


@pytest.fixture
def client(web_client, test_db):
    for table in ("moderation_log", "reports", "user_ratings", "messages", "conversations", "listing_photos", "user_listings", "collection_items", "users"):
        test_db.conn.cursor().execute(f"DELETE FROM {table}")
    auth_service._failures.clear()
    return web_client


def post(client, path, **data):
    return client.post(f"/api/auth/{path}", json=data, headers=HEADERS)


def register(client, username="ana_92", email="Ana@Example.pt", password="segredo123", **extra):
    return post(client, "register", username=username, email=email, password=password, **extra)


def test_sign_up_logs_in(client, test_db):
    response = register(client, display_name="Ana")
    assert response.status_code == 201
    user = response.get_json()
    assert (user["username"], user["email"], user["display_name"]) == ("ana_92", "ana@example.pt", "Ana")
    assert "password_hash" not in user and "password" not in user
    assert client.get("/api/auth/me").get_json()["username"] == "ana_92"

    # stored hashed, never as typed
    stored = test_db.conn.cursor().execute("SELECT password_hash FROM users").fetchone()[0]
    assert stored != "segredo123" and stored.startswith("scrypt:")


@pytest.mark.parametrize("fields, error", [
    ({"username": "ab"}, "username_invalid"),                 # too short
    ({"username": "ana silva"}, "username_invalid"),          # no spaces
    ({"email": "not-an-email"}, "email_invalid"),
    ({"password": "1234567"}, "password_short"),
])
def test_sign_up_rules(client, fields, error):
    response = register(client, **fields)
    assert (response.status_code, response.get_json()["error"]) == (400, error)


def test_username_and_email_are_unique(client, test_db):
    register(client)
    assert register(client, email="other@example.pt").get_json()["error"] == "username_taken"
    assert register(client, username="ANA_92", email="x@example.pt").get_json()["error"] == "username_taken"
    assert register(client, username="other").get_json()["error"] == "email_taken"     # case doesn't matter
    # the database refuses it too (two sign-ups at the same moment)
    with pytest.raises(psycopg.errors.UniqueViolation):
        test_db.conn.cursor().execute("INSERT INTO users (username, email, display_name) VALUES ('Ana_92', 'y@x.pt', 'A')")


def test_log_in_with_username_or_email_and_log_out(client):
    register(client)
    post(client, "logout")
    assert client.get("/api/auth/me").get_json() is None

    assert post(client, "login", login="ana_92", password="segredo123").status_code == 200
    post(client, "logout")
    assert post(client, "login", login="ANA@example.pt", password="segredo123").get_json()["username"] == "ana_92"
    post(client, "logout")
    assert post(client, "login", login="Ana_92", password="segredo123").get_json()["username"] == "ana_92"


def test_wrong_password_and_lock_out(client):
    register(client)
    post(client, "logout")
    for _ in range(auth_service.MAX_FAILURES):
        response = post(client, "login", login="ana_92", password="wrong-password")
        assert (response.status_code, response.get_json()["error"]) == (400, "login_failed")
    # locked now, even with the right password
    response = post(client, "login", login="ana_92", password="segredo123")
    assert (response.status_code, response.get_json()["error"]) == (429, "login_locked")
    # an unknown user gets the same answer as a wrong password (doesn't reveal who has an account)
    assert post(client, "login", login="nobody", password="segredo123").get_json()["error"] == "login_failed"


def test_blocked_account_is_logged_out(client, test_db):
    register(client)
    test_db.conn.cursor().execute("UPDATE users SET is_active = false")
    assert client.get("/api/auth/me").get_json() is None
    assert post(client, "login", login="ana_92", password="segredo123").get_json()["error"] == "login_failed"


def test_changes_need_our_pages_header(client):
    # a form on another site can't add this header: the request is refused
    response = client.post("/api/auth/register", json={"username": "x_user", "email": "x@x.pt", "password": "segredo123"})
    assert (response.status_code, response.get_json()["error"]) == (403, "missing_request_header")
