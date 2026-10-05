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


def test_sign_ups_from_one_address_are_limited(client):
    """Accounts made in bulk (spam, other people's e-mail addresses): at most MAX_SIGNUPS tries per hour."""
    for i in range(auth_service.MAX_SIGNUPS):
        assert register(client, username=f"user_{i}", email=f"user_{i}@example.pt").status_code == 201
    response = register(client, username="one_more", email="one_more@example.pt")
    assert (response.status_code, response.get_json()["error"]) == (429, "register_locked")


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


@pytest.fixture
def mails(monkeypatch):
    """E-mails the app sends, as (to, subject, text), instead of sending them (at once, not in the background)."""
    sent = []
    monkeypatch.setattr(auth_service.mail_service, "send", lambda *mail: sent.append(mail) or False)
    monkeypatch.setattr(auth_service, "in_background", lambda work, *args: work(*args))
    return sent


def test_asking_for_a_reset_doesnt_wait_for_the_mail(client, monkeypatch):
    """Sending takes seconds and only happens for real accounts: done in the background, the answer
    takes as long either way (it doesn't tell whether the address has an account)."""
    import threading
    import time
    register(client)
    sent = threading.Event()
    monkeypatch.setattr(auth_service.mail_service, "send", lambda *mail: time.sleep(2) or sent.set())
    started = time.monotonic()
    assert post(client, "forgot", email="ana@example.pt").get_json() == {"ok": True}
    assert time.monotonic() - started < 1.5
    assert sent.wait(5)                                                    # and it does go out


def reset_token(mail):
    return mail[2].split("/account?reset=")[1].split()[0]


def test_forgotten_password(client, mails):
    register(client)
    for _ in range(auth_service.MAX_FAILURES):                             # locked out by wrong passwords
        post(client, "login", login="ana_92", password="wrong-password")
    post(client, "logout")

    # an unknown email gets the same answer, and no mail
    assert post(client, "forgot", email="nobody@example.pt").get_json() == {"ok": True}
    assert post(client, "forgot", email=" ANA@example.pt ", lang="en").get_json() == {"ok": True}
    [mail] = mails
    assert mail[0] == "ana@example.pt" and mail[1] == "New password" and "ana_92" in mail[2]
    token = reset_token(mail)

    assert post(client, "reset", token=token, password="curta").get_json()["error"] == "password_short"
    assert post(client, "reset", token=token + "x", password="nova-senha-1").get_json()["error"] == "reset_invalid"
    assert post(client, "reset", token=token, password="nova-senha-1").get_json()["username"] == "ana_92"
    assert client.get("/api/auth/me").get_json()["username"] == "ana_92"   # logged in

    # the link worked once; the new password works, the lock-out is gone
    assert post(client, "reset", token=token, password="outra-senha-2").get_json()["error"] == "reset_invalid"
    post(client, "logout")
    assert post(client, "login", login="ana_92", password="nova-senha-1").status_code == 200


def test_a_new_password_logs_out_every_other_session(client, mails):
    """Someone with a copy of the login cookie (another computer, a stolen one) is out once the password changes."""
    from app.web import app
    register(client)
    other = app.test_client()
    assert post(other, "login", login="ana_92", password="segredo123").status_code == 200
    assert other.get("/api/auth/me").get_json()["username"] == "ana_92"

    post(client, "forgot", email="ana@example.pt")
    post(client, "reset", token=reset_token(mails[0]), password="nova-senha-1")
    assert client.get("/api/auth/me").get_json()["username"] == "ana_92"   # the one who changed it stays in
    assert other.get("/api/auth/me").get_json() is None
    assert other.get("/api/collection").status_code == 401


def test_reset_link_expires_and_requests_are_limited(client, mails, monkeypatch):
    register(client)
    post(client, "forgot", email="ana@example.pt")
    monkeypatch.setattr(auth_service, "RESET_SECONDS", -1)                  # an hour later
    assert post(client, "reset", token=reset_token(mails[0]), password="nova-senha-1").get_json()["error"] == "reset_invalid"

    for _ in range(auth_service.MAX_FAILURES - 1):
        post(client, "forgot", email="ana@example.pt")
    response = post(client, "forgot", email="ana@example.pt")
    assert (response.status_code, response.get_json()["error"]) == (429, "reset_locked")


def test_huge_logins_and_passwords_are_refused_and_not_kept(client):
    """A request can be ~100 MB: such a login mustn't be kept in memory (the lock-out's records), nor
    sent to the database or hashed."""
    register(client)
    post(client, "logout")
    huge = "a" * 100_000
    assert post(client, "login", login=huge, password="segredo123").get_json()["error"] == "login_failed"
    assert post(client, "login", login="ana_92", password=huge).get_json()["error"] == "login_failed"
    assert all(len(login) <= auth_service.MAX_LOGIN for _, login in auth_service._failures)
    long_password = "p" * (auth_service.MAX_PASSWORD + 1)
    assert register(client, username="bea_1", email="bea@example.pt", password=long_password).get_json()["error"] == "password_long"
    assert post(client, "reset", token="x", password=long_password).get_json()["error"] == "password_long"


def test_only_photo_uploads_may_be_big(client):
    """JSON bodies are small: past 1 MB the request is refused before it's read (photos are multipart)."""
    response = post(client, "login", login="a" * 2_000_000, password="segredo123")
    assert response.status_code == 413


def test_lock_out_records_are_bounded(client, monkeypatch):
    """Wrong passwords for many different logins: the oldest records go, memory doesn't grow forever."""
    monkeypatch.setattr(auth_service, "MAX_TRACKED", 3)
    for i in range(8):
        with pytest.raises(auth_service.AccountError):
            auth_service.authenticate(f"user_{i}", "wrong-password", ip="203.0.113.5")
    assert len(auth_service._failures) <= 3
    assert ("203.0.113.5", "user_7") in auth_service._failures            # the latest kept


def test_blocked_account_is_logged_out(client, test_db):
    register(client)
    test_db.conn.cursor().execute("UPDATE users SET is_active = false")
    assert client.get("/api/auth/me").get_json() is None
    assert post(client, "login", login="ana_92", password="segredo123").get_json()["error"] == "login_failed"


@pytest.mark.parametrize("body", ["[1, 2]", '"text"', "7", "null"])
def test_a_json_body_that_isnt_an_object_is_refused(client, body):
    """Our pages always send {…}; anything else is a 400, not a server error in the route."""
    response = client.post("/api/auth/login", data=body, content_type="application/json", headers=HEADERS)
    assert (response.status_code, response.get_json()["error"]) == (400, "body_invalid")


def test_changes_need_our_pages_header(client):
    # a form on another site can't add this header: the request is refused
    response = client.post("/api/auth/register", json={"username": "x_user", "email": "x@x.pt", "password": "segredo123"})
    assert (response.status_code, response.get_json()["error"]) == (403, "missing_request_header")
