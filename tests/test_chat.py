"""Marketplace conversations and the purchase steps (on a throwaway database)."""
import io

import pytest
from PIL import Image

from app.services import chat_service
from helpers import HEADERS, jpeg, log_in, new_listing, sign_up


@pytest.fixture
def deal(market):
    """A seller with a listing, and a buyer (logged in at the end)."""
    client = market["client"]
    sign_up(client, "seller")
    listing = new_listing(market).get_json()
    client.post("/api/auth/logout", headers=HEADERS)
    sign_up(client, "buyer")
    return {**market, "listing": listing}


def start(client, listing_id, **data):
    return client.post(f"/api/listings/{listing_id}/conversation", json=data, headers=HEADERS)


def step(client, conversation_id, action):
    return client.post(f"/api/conversations/{conversation_id}/steps", json={"action": action}, headers=HEADERS)


def listing_status(m):
    return m["db"].execute("SELECT status FROM user_listings WHERE id = ?", m["listing"]["id"]).fetchone()[0]


def events(client, conversation_id):
    return [msg["event"] for msg in client.get(f"/api/conversations/{conversation_id}").get_json()["messages"] if msg["event"]]


def test_a_purchase_from_buy_to_completed(deal):
    client = deal["client"]
    conversation_id = start(client, deal["listing"]["id"], message="Ainda está disponível?", buy=True).get_json()["id"]
    buyer_view = client.get(f"/api/conversations/{conversation_id}").get_json()
    assert (buyer_view["role"], buyer_view["deal_status"], buyer_view["other_username"]) == ("buyer", "requested", "seller")
    assert buyer_view["steps"] == ["cancel"]

    log_in(client, "seller")
    seller_view = client.get(f"/api/conversations/{conversation_id}").get_json()
    assert seller_view["messages"][0]["body"] == "Ainda está disponível?"
    assert sorted(seller_view["steps"]) == ["accept", "decline"]
    assert step(client, conversation_id, "accept").get_json()["deal_status"] == "accepted"
    assert listing_status(deal) == "reserved"
    assert step(client, conversation_id, "sent").get_json()["deal_status"] == "sent"

    log_in(client, "buyer")
    assert sorted(client.get(f"/api/conversations/{conversation_id}").get_json()["steps"]) == ["problem", "received"]
    done = step(client, conversation_id, "received").get_json()
    assert done["deal_status"] == "completed" and done["completed_at"]
    assert listing_status(deal) == "sold"
    assert events(client, conversation_id) == ["request", "accept", "sent", "received"]
    # the buyer still sees what they bought; strangers don't see a sold listing
    assert client.get(f"/api/listings/{deal['listing']['id']}").status_code == 200
    sign_up(client, "stranger")
    assert client.get(f"/api/listings/{deal['listing']['id']}").status_code == 404


def test_each_side_only_takes_its_own_steps(deal):
    client = deal["client"]
    conversation_id = start(client, deal["listing"]["id"], buy=True).get_json()["id"]
    response = step(client, conversation_id, "accept")                 # the buyer can't accept
    assert (response.status_code, response.get_json()["error"]) == (409, "step_not_allowed")
    log_in(client, "seller")
    assert step(client, conversation_id, "received").status_code == 409  # nor the seller confirm receipt
    assert step(client, conversation_id, "made_up").status_code == 409


def test_cancelling_an_accepted_purchase_puts_the_listing_back(deal):
    client = deal["client"]
    conversation_id = start(client, deal["listing"]["id"], buy=True).get_json()["id"]
    log_in(client, "seller")
    step(client, conversation_id, "accept")
    log_in(client, "buyer")
    assert step(client, conversation_id, "cancel").get_json()["deal_status"] == "cancelled"
    assert listing_status(deal) == "active"
    # and the buyer may ask again later
    assert step(client, conversation_id, "request").get_json()["deal_status"] == "requested"


def test_two_buyers_one_copy(deal):
    client = deal["client"]
    first = start(client, deal["listing"]["id"], buy=True).get_json()["id"]
    sign_up(client, "buyer2")
    second = start(client, deal["listing"]["id"], buy=True).get_json()["id"]

    log_in(client, "seller")
    step(client, first, "accept")
    # reserved for the first buyer: no accepting the second, and no new conversations
    assert "accept" not in client.get(f"/api/conversations/{second}").get_json()["steps"]
    assert step(client, second, "accept").get_json()["error"] == "step_not_allowed"
    step(client, first, "sent")
    log_in(client, "buyer")
    step(client, first, "received")

    log_in(client, "buyer2")
    view = client.get(f"/api/conversations/{second}").get_json()
    assert (view["deal_status"], view["steps"]) == ("declined", [])
    assert events(client, second)[-1] == "listing_sold"
    sign_up(client, "buyer3")
    assert start(client, deal["listing"]["id"]).get_json()["error"] == "listing_unavailable"


def test_sent_purchases_complete_by_themselves_after_7_days(deal):
    client = deal["client"]
    conversation_id = start(client, deal["listing"]["id"], buy=True).get_json()["id"]
    log_in(client, "seller")
    step(client, conversation_id, "accept")
    step(client, conversation_id, "sent")

    deal["db"].execute("UPDATE conversations SET sent_at = utcnow() - interval '6 days' WHERE id = ?", conversation_id)
    assert chat_service.complete_overdue() == 0
    deal["db"].execute("UPDATE conversations SET sent_at = utcnow() - interval '8 days' WHERE id = ?", conversation_id)
    assert chat_service.complete_overdue() == 1
    assert client.get(f"/api/conversations/{conversation_id}").get_json()["deal_status"] == "completed"
    assert listing_status(deal) == "sold"


def test_a_reported_problem_stops_the_automatic_completion(deal):
    client = deal["client"]
    conversation_id = start(client, deal["listing"]["id"], buy=True).get_json()["id"]
    log_in(client, "seller")
    step(client, conversation_id, "accept")
    step(client, conversation_id, "sent")
    log_in(client, "buyer")
    assert step(client, conversation_id, "problem").get_json()["deal_status"] == "problem"
    deal["db"].execute("UPDATE conversations SET sent_at = utcnow() - interval '30 days' WHERE id = ?", conversation_id)
    assert chat_service.complete_overdue() == 0


def test_unread_messages(deal):
    client = deal["client"]
    conversation_id = start(client, deal["listing"]["id"], message="Olá!").get_json()["id"]
    assert client.get("/api/conversations/unread").get_json()["count"] == 0      # my own message

    log_in(client, "seller")
    assert client.get("/api/conversations/unread").get_json()["count"] == 1
    assert client.get("/api/conversations").get_json()[0]["last_body"] == "Olá!"
    client.get(f"/api/conversations/{conversation_id}")                           # opening it reads it
    assert client.get("/api/conversations/unread").get_json()["count"] == 0
    reply = client.post(f"/api/conversations/{conversation_id}/messages", json={"body": "Sim!"}, headers=HEADERS)
    assert reply.get_json()["messages"][-1]["body"] == "Sim!"


def test_conversations_are_private(deal):
    client = deal["client"]
    conversation_id = start(client, deal["listing"]["id"], message="Olá").get_json()["id"]
    sign_up(client, "someone_else")
    assert client.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert client.post(f"/api/conversations/{conversation_id}/messages", json={"body": "x"}, headers=HEADERS).status_code == 404
    assert client.get("/api/conversations").get_json() == []


def test_message_rules(deal):
    client = deal["client"]
    log_in(client, "seller")
    assert start(client, deal["listing"]["id"], message="x").get_json()["error"] == "own_listing"
    log_in(client, "buyer")
    conversation_id = start(client, deal["listing"]["id"]).get_json()["id"]
    send = lambda body: client.post(f"/api/conversations/{conversation_id}/messages", json={"body": body}, headers=HEADERS)
    assert send("   ").get_json()["error"] == "message_empty"
    assert send("x" * 2001).get_json()["error"] == "message_long"
    client.post("/api/auth/logout", headers=HEADERS)
    assert start(client, deal["listing"]["id"], message="x").status_code == 401


def send_photos(client, conversation_id, n, body=""):
    files = [(io.BytesIO(jpeg(gps=True)), f"photo{i}.jpg") for i in range(n)]
    return client.post(f"/api/conversations/{conversation_id}/messages", data={"body": body, "photos": files},
                       headers=HEADERS, content_type="multipart/form-data")


def test_photos_in_a_conversation(deal):
    """The buyer asks for more pictures; the seller sends them. Only the two sides (and moderators) see them."""
    client = deal["client"]
    conversation_id = start(client, deal["listing"]["id"], message="Pode mandar fotos do disco?").get_json()["id"]
    log_in(client, "seller")
    sent = send_photos(client, conversation_id, 2, body="Aqui estão").get_json()["messages"][-1]
    assert sent["body"] == "Aqui estão" and len(sent["photos"]) == 2
    photo_only = send_photos(client, conversation_id, 1).get_json()["messages"][-1]
    assert photo_only["body"] is None and len(photo_only["photos"]) == 1

    full, thumb = client.get(sent["photos"][0]["url"]), client.get(sent["photos"][0]["thumb_url"])
    assert full.status_code == 200 and full.mimetype == "image/jpeg" and "private" in full.headers["Cache-Control"]
    assert len(thumb.data) < len(full.data)
    assert not Image.open(io.BytesIO(full.data)).getexif()          # EXIF (GPS) removed, as for listings

    log_in(client, "buyer")
    listed = {c["id"]: c for c in client.get("/api/conversations").get_json()}[conversation_id]
    assert listed["last_photos"] is True and listed["unread"] == 2
    assert client.get(sent["photos"][1]["url"]).status_code == 200

    # not through /media (anyone with the address), not for others, not from another conversation's address
    key = deal["db"].execute("SELECT photo_key FROM message_photos ORDER BY id LIMIT 1").fetchone()[0]
    assert key.startswith(f"chats/{conversation_id}/") and client.get(f"/media/{key}").status_code == 404
    sign_up(client, "stranger")
    assert client.get(sent["photos"][0]["url"]).status_code == 404
    deal["db"].execute("UPDATE users SET role = 'moderator' WHERE username = 'stranger'")
    assert client.get(sent["photos"][0]["url"]).status_code == 200      # a moderator looking into a problem
    other = client.get(sent["photos"][0]["url"].replace(f"/conversations/{conversation_id}/", "/conversations/999999/"))
    assert other.status_code == 404


def test_photo_rules(deal):
    client = deal["client"]
    conversation_id = start(client, deal["listing"]["id"], message="Olá").get_json()["id"]
    too_many = send_photos(client, conversation_id, 6)
    assert (too_many.status_code, too_many.get_json()["error"]) == (400, "message_photos_many")
    not_a_photo = client.post(f"/api/conversations/{conversation_id}/messages", headers=HEADERS,
                              data={"photos": [(io.BytesIO(b"not an image"), "x.jpg")]}, content_type="multipart/form-data")
    assert (not_a_photo.status_code, not_a_photo.get_json()["error"]) == (400, "photo_type")
    assert not list(deal["dir"].glob("chats/**/*.jpg"))      # nothing kept from refused messages
    assert len(client.get(f"/api/conversations/{conversation_id}").get_json()["messages"]) == 1
