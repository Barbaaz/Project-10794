"""Accounts: sign up, log in / out, lock-out, and the protection against requests from other sites."""
import psycopg
import pytest

from app.services import auth_service
from helpers import HEADERS


@pytest.fixture
def client(web_client, test_db):
    for table in ("moderation_log", "reports", "user_ratings", "messages", "conversations", "listing_photos", "user_listings", "collection_items", "follows", "users"):
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


def test_changing_the_password_while_logged_in(client):
    from app.web import app
    assert post(client, "password", current="segredo123", password="nova-senha-1").status_code == 401
    register(client)
    other = app.test_client()
    post(other, "login", login="ana_92", password="segredo123")

    assert post(client, "password", current="segredo123", password="curta").get_json()["error"] == "password_short"
    response = post(client, "password", current="errada-123", password="nova-senha-1")
    assert (response.status_code, response.get_json()["error"]) == (400, "password_wrong")
    assert post(client, "password", current="segredo123", password="nova-senha-1").get_json()["username"] == "ana_92"

    assert client.get("/api/auth/me").get_json()["username"] == "ana_92"   # this session stays
    assert other.get("/api/auth/me").get_json() is None                    # the others are logged out
    post(client, "logout")
    assert post(client, "login", login="ana_92", password="segredo123").get_json()["error"] == "login_failed"
    assert post(client, "login", login="ana_92", password="nova-senha-1").status_code == 200


def test_the_current_password_cant_be_guessed_there(client):
    """Wrong current passwords count like wrong logins: locked after MAX_FAILURES."""
    register(client)
    for _ in range(auth_service.MAX_FAILURES):
        post(client, "password", current="errada-123", password="nova-senha-1")
    response = post(client, "password", current="segredo123", password="nova-senha-1")
    assert (response.status_code, response.get_json()["error"]) == (429, "login_locked")


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


def test_editing_the_profile(market):
    """User, 2026-10-12: the display name and the location can be changed (an empty name is the username)."""
    from helpers import HEADERS, sign_up
    client = market["client"]
    sign_up(client, "edita")
    edit = lambda **fields: client.patch("/api/auth/profile", json=fields, headers=HEADERS)
    assert edit(display_name="  Edite Silva ", location="Braga").get_json()["display_name"] == "Edite Silva"
    profile = client.get("/api/users/edita").get_json()
    assert (profile["display_name"], profile["location"]) == ("Edite Silva", "Braga")
    assert edit(display_name="", location="  ").get_json()["display_name"] == "edita"
    assert client.get("/api/users/edita").get_json()["location"] is None
    assert edit(location="x" * 101).get_json()["error"] == "location_long"
    assert edit(display_name="x" * 101).status_code == 400
    assert client.patch("/api/auth/profile", json={"location": "Faro"}).status_code in (400, 403)   # no X-Requested-With
    client.post("/api/auth/logout", headers=HEADERS)
    assert edit(location="Faro").status_code == 401


def test_gaming_accounts_on_the_profile(market):
    """User, 2026-10-13: gamer names and channels on the profile, typed or pasted as links; links only to
    the services' own pages; empty takes one off; gone with the account."""
    from helpers import HEADERS, sign_up
    client = market["client"]
    user_id = sign_up(client, "gamer_tags")["id"]
    edit = lambda **fields: client.patch("/api/auth/profile", json=fields, headers=HEADERS)
    mine = edit(psn="Gamer_Tags", xbox="Gamer Tags#1234", steam="https://steamcommunity.com/id/gamertags/",
                nintendo="1234 5678 9012", epic="Gamer Tags", youtube="https://www.youtube.com/@GamerTags?si=x",
                twitch="twitch.tv/gamer_tags").get_json()
    assert mine["accounts"] == {"psn": "Gamer_Tags", "xbox": "Gamer Tags#1234", "steam": "id/gamertags",
                                "nintendo": "SW-1234-5678-9012", "epic": "Gamer Tags", "youtube": "@GamerTags",
                                "twitch": "gamer_tags"}
    shown = {a["kind"]: (a["name"], a["url"]) for a in client.get("/api/users/gamer_tags").get_json()["accounts"]}
    assert shown["psn"] == ("Gamer_Tags", None)
    assert shown["steam"] == ("gamertags", "https://steamcommunity.com/id/gamertags")
    assert shown["youtube"] == ("@GamerTags", "https://www.youtube.com/@GamerTags")
    assert shown["twitch"] == ("gamer_tags", "https://www.twitch.tv/gamer_tags")

    # a number-only page shows the service's name; other changes leave the accounts as they were
    assert edit(steam="steamcommunity.com/profiles/76561197960287930", location="Porto").get_json()["accounts"]["steam"] \
        == "profiles/76561197960287930"
    steam = [a for a in client.get("/api/users/gamer_tags").get_json()["accounts"] if a["kind"] == "steam"][0]
    assert steam == {"kind": "steam", "name": None, "url": "https://steamcommunity.com/profiles/76561197960287930"}
    assert len(edit(display_name="Gamer").get_json()["accounts"]) == 7

    # nothing that isn't the service's name: no other site, no script
    for kind, text in (("twitch", "https://evil.example/x"), ("youtube", "javascript:alert(1)"), ("psn", "a"),
                       ("steam", "https://evil.example/id/x"), ("nintendo", "12345"), ("epic", "<b>x</b>")):
        assert edit(**{kind: text}).get_json()["error"] == f"{kind}_invalid", kind
    assert edit(psn="", twitch=None).get_json()["accounts"].keys() == {"xbox", "steam", "nintendo", "epic", "youtube"}

    client.post("/api/auth/delete", json={"password": "segredo123"}, headers=HEADERS)
    assert market["db"].execute("SELECT accounts_json FROM users WHERE id = ?", user_id).fetchone()[0] is None


def test_a_profile_picture(market):
    """User, 2026-10-12: a profile picture, made a square without metadata; replaced, removed, and gone with
    the account; a moderator can remove it."""
    import io
    from PIL import Image
    from helpers import HEADERS, jpeg, log_in, sign_up
    from app.services import moderation_service
    client = market["client"]
    sign_up(client, "pictured")
    upload = lambda data: client.post("/api/auth/avatar", data={"avatar": (io.BytesIO(data), "me.jpg")},
                                      headers=HEADERS, content_type="multipart/form-data")
    first = upload(jpeg(1200, 800, gps=True)).get_json()["avatar"]
    picture = client.get(first)
    image = Image.open(io.BytesIO(picture.data))
    picture.close()                                         # the file is free to go (Windows)
    assert (picture.status_code, image.size, image.getexif().get(0x8825)) == (200, (256, 256), None)   # no GPS
    assert client.get("/api/users/pictured").get_json()["avatar"] == first
    second = upload(jpeg()).get_json()["avatar"]
    assert second != first and client.get(first).status_code == 404               # the old file goes
    assert upload(b"not a picture").get_json()["error"] == "photo_type"
    assert client.delete("/api/auth/avatar", headers=HEADERS).get_json()["avatar"] is None
    assert client.get(second).status_code == 404

    third = upload(jpeg()).get_json()["avatar"]                                     # one that breaks the rules
    user_id = client.get("/api/auth/me").get_json()["id"]
    sign_up(client, "mod_pic")
    market["db"].execute("UPDATE users SET role = 'moderator' WHERE username = 'mod_pic'")
    moderator_id = client.get("/api/auth/me").get_json()["id"]
    moderation_service.act(moderator_id, "remove_avatar", user_id)
    assert client.get("/api/users/pictured").get_json()["avatar"] is None and client.get(third).status_code == 404

    log_in(client, "pictured")
    fourth = upload(jpeg()).get_json()["avatar"]
    client.post("/api/auth/delete", json={"password": "segredo123"}, headers=HEADERS)
    assert client.get(fourth).status_code == 404                                     # gone with the account
