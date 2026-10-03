"""Games no store sells, created from IGDB by a seller (app/services/igdb_game_service.py; IGDB replaced)."""
import pytest

from helpers import HEADERS, sign_up
from app.services import igdb_game_service

OKAMI = {"id": 9001, "name": "Okami", "first_release_date": 1145750400, "cover": {"image_id": "co1abc"},
         "platforms": [8, 5, 999], "game_type": 0, "summary": "A wolf.", "genres": [{"name": "Adventure"}]}


@pytest.fixture
def igdb(market, monkeypatch):
    """IGDB answers with Okami (PS2, Wii, and a platform we don't have); games made here are removed after."""
    asked = []

    def query(body):
        asked.append(body)
        return [OKAMI] if "9001" in body or "search" in body else []
    monkeypatch.setattr(igdb_game_service, "query", query)
    yield market | {"asked": asked}
    c = market["db"]
    c.execute("DELETE FROM user_listings WHERE game_id IN (SELECT id FROM games WHERE igdb_id = 9001)")
    c.execute("DELETE FROM game_editions WHERE game_id IN (SELECT id FROM games WHERE igdb_id = 9001)")
    c.execute("DELETE FROM games WHERE igdb_id = 9001")


def test_search_lists_our_platforms_only(igdb):
    client = igdb["client"]
    assert client.get("/api/igdb/games?q=okami").status_code == 401        # an account first
    sign_up(client, "retro_seller")
    [game] = client.get("/api/igdb/games?q=okami").get_json()
    assert game["name"] == "Okami" and game["year"] == 2006
    assert game["cover"].endswith("/co1abc.jpg")
    assert [p["code"] for p in game["platforms"]] == ["PS2", "Wii"]        # 999 isn't one of ours
    assert client.get("/api/igdb/games?q=o").get_json() == []              # too short: IGDB isn't asked


def test_picking_a_platform_creates_the_game_once(igdb):
    client = igdb["client"]
    sign_up(client, "retro_seller2")
    post = lambda platform: client.post("/api/igdb/games", headers=HEADERS, json={"igdb_id": 9001, "platform": platform})
    made = post("PS2").get_json()
    game = client.get(f"/api/games/{made['game_id']}").get_json()
    assert (game["title"], game["platform"], game["summary"]) == ("Okami", "PS2", "A wolf.")
    assert [e["name"] for e in game["editions"]] == ["Standard"]            # kept though no store sells it
    assert post("PS2").get_json() == made                                   # the same game, not a second one
    assert post("Wii").get_json()["game_id"] != made["game_id"]            # each platform its own game
    assert post("PS5").get_json()["error"] == "not_found"                   # not on that platform
    assert post("Atari").get_json()["error"] == "platform_invalid"

    # it can be sold like any game (photos aside: the listing form needs them)
    c = igdb["db"]
    assert c.execute("SELECT created_by FROM games WHERE id = ?", made["game_id"]).fetchone()[0] is not None


def test_games_per_day(igdb, monkeypatch):
    client = igdb["client"]
    sign_up(client, "retro_seller3")
    monkeypatch.setattr(igdb_game_service, "MAX_PER_DAY", 1)
    ok = client.post("/api/igdb/games", headers=HEADERS, json={"igdb_id": 9001, "platform": "PS2"})
    assert ok.status_code == 200
    again = client.post("/api/igdb/games", headers=HEADERS, json={"igdb_id": 9001, "platform": "Wii"})
    assert again.status_code == 429 and again.get_json()["error"] == "games_per_day"
