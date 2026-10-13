"""database/demo.py --profile (user, 2026-10-13): a user's public side copied into a test copy's demo
file, so testers see a full profile; never their e-mail, password or Steam / PSN ids."""
import io
import json

from PIL import Image

from database import demo
from helpers import HEADERS, sign_up


def test_a_profile_goes_through_the_demo_file_without_its_login(market):
    client, c = market["client"], market["db"]
    sign_up(client, "Showcased")
    client.patch("/api/auth/profile", json={"display_name": "Show Case", "location": "Porto", "psn": "Show_Case"},
                 headers=HEADERS)
    picture = io.BytesIO()
    Image.new("RGB", (300, 300), "red").save(picture, "JPEG")
    client.post("/api/auth/avatar", data={"avatar": (io.BytesIO(picture.getvalue()), "me.jpg")}, headers=HEADERS)
    client.post("/api/collection", json={"edition_id": market["edition"], "kind": "owned", "hours": 12.5}, headers=HEADERS)
    client.put("/api/collection/settings", json={"public": True}, headers=HEADERS)
    c.execute("UPDATE users SET steam_id = '7656', psn_online_id = 'Show_Case' WHERE username = 'Showcased'")

    profile = json.loads(json.dumps(demo.export_profile(c, "showcased")))         # as it's written to the file
    assert "email" not in profile["user"] and "password_hash" not in profile["user"]
    assert not {"steam_id", "psn_online_id", "psn_account_id"} & set(profile["user"])

    client.post("/api/auth/logout", headers=HEADERS)
    c.execute("DELETE FROM collection_items")
    c.execute("DELETE FROM users")
    demo.import_profile(c, profile)
    demo.import_profile(c, profile)                     # already there: left as it is

    shown = client.get("/api/users/Showcased").get_json()
    assert (shown["display_name"], shown["location"]) == ("Show Case", "Porto")
    assert shown["accounts"] == [{"kind": "psn", "name": "Show_Case", "url": None}]
    assert client.get(shown["avatar"]).status_code == 200
    assert client.get("/api/users/Showcased/collection").get_json()["stats"]["owned"] == 1
    email, password, alerts, count = c.execute(
        "SELECT email, password_hash, wish_alerts, (SELECT count(*) FROM users) FROM users").fetchone()
    assert (email, password, alerts, count) == ("showcased@profile.invalid", None, False, 1)
    for password in ("", "segredo123"):
        login = client.post("/api/auth/login", json={"login": "Showcased", "password": password}, headers=HEADERS)
        assert login.get_json()["error"] == "login_failed"
