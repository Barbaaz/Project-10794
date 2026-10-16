"""The Contactos page (user, 2026-10-16): messages to the site's team, read in /admin; on a throwaway database."""
import pytest

from helpers import HEADERS, log_in, sign_up
from app.services import contact_service

MESSAGE = {"name": "Ana Leitora", "email": "Ana@Example.pt", "topic": "store", "body": "Podiam acrescentar a loja X?"}


@pytest.fixture
def mails(market, monkeypatch):
    """The e-mails sent to the team ([(to, subject, text)]); the hourly count starts empty."""
    sent = []
    monkeypatch.setattr(contact_service, "_sent", {})
    monkeypatch.setattr(contact_service.config, "ALERT_EMAIL", "equipa@example.pt")
    monkeypatch.setattr(contact_service.mail_service, "send", lambda *args: sent.append(args) or False)
    return sent


def send(client, **changes):
    return client.post("/api/contact", json={**MESSAGE, **changes}, headers=HEADERS)


def test_anyone_can_write_and_the_team_is_told(market, mails):
    client, db = market["client"], market["db"]
    assert send(client).get_json() == {"ok": True}
    row = db.execute("SELECT user_id, name, email, topic, body FROM contact_messages").fetchone()
    assert tuple(row) == (None, "Ana Leitora", "ana@example.pt", "store", "Podiam acrescentar a loja X?")
    to, subject, text = mails[0]
    assert to == "equipa@example.pt" and "store" in subject and "Responder para: ana@example.pt" in text


def test_wrong_messages(market, mails):
    client = market["client"]
    for changes, error in (({"name": " "}, "contact_name_invalid"), ({"name": "x" * 101}, "contact_name_invalid"),
                           ({"email": "nope"}, "email_invalid"), ({"topic": "spam"}, "contact_topic_invalid"),
                           ({"body": "curto"}, "contact_body_short"), ({"body": "x" * 4001}, "contact_body_long")):
        assert send(client, **changes).get_json() == {"error": error}, changes
    assert market["db"].execute("SELECT count(*) FROM contact_messages").fetchone()[0] == 0


def test_bots_and_floods(market, mails):
    client, db = market["client"], market["db"]
    assert send(client, website="http://spam.example").get_json() == {"ok": True}     # thanked, not kept
    assert db.execute("SELECT count(*) FROM contact_messages").fetchone()[0] == 0 and not mails
    for _ in range(contact_service.MAX_PER_HOUR):
        assert send(client).status_code == 200
    response = send(client)
    assert response.status_code == 429 and response.get_json() == {"error": "contact_too_many"}


def test_the_team_reads_and_marks_them(market, mails):
    client, db = market["client"], market["db"]
    writer = sign_up(client, "writer")
    send(client)                                             # logged in: linked to the account
    assert client.get("/api/mod/contact").status_code == 403
    sign_up(client, "helper")
    db.execute("UPDATE users SET role = 'moderator' WHERE username = 'helper'")
    answer = client.get("/api/mod/contact").get_json()
    assert answer["open"] == 1 and [(m["username"], m["topic"]) for m in answer["items"]] == [("writer", "store")]
    message_id = answer["items"][0]["id"]
    assert client.post(f"/api/mod/contact/{message_id}", json={"handled": True}, headers=HEADERS).get_json() == {"ok": True}
    assert client.get("/api/mod/contact").get_json() == {"items": [], "open": 0}
    assert client.get("/api/mod/contact?handled=1").get_json()["items"][0]["handled_by"] == "helper"
    assert client.post("/api/mod/contact/999999", json={"handled": True}, headers=HEADERS).status_code == 404

    log_in(client, "writer")                                 # theirs: in their data, gone with the account
    assert client.get("/api/auth/export").get_json()["contact_messages"][0]["body"] == MESSAGE["body"]
    assert client.post("/api/auth/delete", json={"password": "segredo123"}, headers=HEADERS).status_code == 200
    assert db.execute("SELECT count(*) FROM contact_messages WHERE user_id = ?", writer["id"]).fetchone()[0] == 0


def test_the_page(market):
    page = market["client"].get("/contact")
    assert page.status_code == 200 and b"/static/pages/contact.js" in page.data and b'href="/contact"' in page.data
