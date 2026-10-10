"""Importing Steam games into the collection, with Steam and IGDB faked; on a throwaway database."""
import pytest

from app.services import steam_service
from helpers import HEADERS, sign_up


@pytest.fixture
def steam(market, monkeypatch):
    """Two PC games of ours (one known to IGDB), and a fake Steam library of four games."""
    c = market["db"]
    pc = c.execute("SELECT id FROM platforms WHERE code = 'PC'").fetchone()[0]
    games = [c.execute("INSERT INTO games (platform_id, title, normalized_title, igdb_id) VALUES (?, ?, ?, ?) RETURNING id",
                       pc, title, key, igdb).fetchone()[0]
             for title, key, igdb in (("Elden Ring", "elden ring", 119133), ("Portal 2", "portal 2", None))]
    steam_service._last.clear()
    asked = []

    def fake_get(path, **params):
        asked.append(path)
        if "ResolveVanity" in path:
            return {"steamid": "76561197960287930", "success": 1} if params["vanityurl"] == "ana" else {"success": 42}
        return {"games": [
            {"appid": 1245620, "name": "ELDEN RING", "playtime_forever": 6012},     # by IGDB's Steam id
            {"appid": 620, "name": "Portal 2", "playtime_forever": 0},             # by name
            {"appid": 400, "name": "Portal", "playtime_forever": 90},              # IGDB knows it, we don't
            {"appid": 9, "name": "Some Tool", "playtime_forever": 0},              # nobody knows it
        ]}
    monkeypatch.setattr(steam_service, "_get", fake_get)
    monkeypatch.setattr(steam_service, "query", lambda body, endpoint="games":
                        [{"game": 119133, "uid": "1245620"}, {"game": 71, "uid": "400"}])
    yield {**market, "games": games, "asked": asked}
    c.execute("DELETE FROM collection_items")
    c.execute("DELETE FROM game_editions WHERE game_id IN (?, ?)", *games)
    c.execute("DELETE FROM games WHERE id IN (?, ?)", *games)


def steam_import(client, profile):
    return client.post("/api/collection/steam", json={"profile": profile}, headers=HEADERS)


def test_matched_games_go_in_as_digital_with_steam_hours(steam):
    client = steam["client"]
    sign_up(client, "ana_steam")
    answer = steam_import(client, "https://steamcommunity.com/id/ana/").get_json()
    assert (answer["total"], answer["added"], answer["updated"]) == (4, 2, 0)
    assert [(m["name"], m["igdb_id"], m["hours"]) for m in answer["missing"]] == \
        [("Portal", 71, 1.5), ("Some Tool", None, None)]          # IGDB-known first: they can be added

    items = {i["game_id"]: i for i in client.get("/api/collection").get_json()["items"]}
    elden, portal = steam["games"]
    assert (items[elden]["kind"], items[elden]["format"], items[elden]["hours"]) == ("owned", "digital", 100.2)
    assert items[portal]["hours"] is None


def test_a_second_import_waits_then_only_raises_hours(steam, monkeypatch):
    client = steam["client"]
    sign_up(client, "rui_steam")
    steam_import(client, "76561197960287930")                     # an id: no name to resolve
    assert "ISteamUser/ResolveVanityURL/v1/" not in steam["asked"]
    assert steam_import(client, "ana").get_json()["error"] == "steam_wait"
    steam_service._last.clear()
    assert steam_import(client, "ana").get_json()["added"] == 0   # already there: nothing twice


def test_private_unknown_and_invalid_profiles(steam, monkeypatch):
    client = steam["client"]
    sign_up(client, "eva_steam")
    assert steam_import(client, "https://steamcommunity.com/id/nobody").get_json()["error"] == "steam_profile_not_found"
    assert steam_import(client, "not a profile!").get_json()["error"] == "steam_profile_invalid"
    real = steam_service._get
    monkeypatch.setattr(steam_service, "_get", lambda path, **p: {"steamid": "1", "success": 1} if "Vanity" in path else {})
    assert steam_import(client, "ana").get_json()["error"] == "steam_private"
    monkeypatch.setattr(steam_service, "_get", real)          # made public on Steam: no wait for a failed try
    assert steam_import(client, "ana").get_json()["added"] == 2


def test_importing_needs_a_login(steam):
    assert steam_import(steam["client"], "ana").status_code == 401
