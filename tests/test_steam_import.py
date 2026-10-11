"""Importing Steam games into the collection, with Steam and IGDB faked; on a throwaway database."""
import pytest

from app.services import igdb_game_service, steam_service
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
            {"appid": 1245620, "name": "ELDEN RING", "playtime_forever": 6012,     # by IGDB's Steam id
             "has_community_visible_stats": True},
            {"appid": 620, "name": "Portal 2", "playtime_forever": 0},             # by name
            {"appid": 400, "name": "Portal", "playtime_forever": 90},              # IGDB knows it, we don't
            {"appid": 9, "name": "Some Tool", "playtime_forever": 0},              # nobody knows it
        ]}
    monkeypatch.setattr(steam_service, "_get", fake_get)
    monkeypatch.setattr(steam_service, "query", lambda body, endpoint="games":
                        [{"game": 119133, "uid": "1245620"}, {"game": 71, "uid": "400"}])
    # IGDB's Portal, made for the collection only
    monkeypatch.setattr(igdb_game_service, "query", lambda body, endpoint="games":
                        [{"id": 71, "name": "Portal", "platforms": [6], "summary": "Thinking with portals"}])
    achievements = {1245620: (12, 42)}
    monkeypatch.setattr(steam_service, "achievements", lambda steamid, appid: achievements.get(appid))
    yield {**market, "games": games, "asked": asked, "achievements": achievements}
    c.execute("DELETE FROM collection_items")
    c.execute("UPDATE users SET steam_id = NULL")
    made = [r[0] for r in c.execute("SELECT id FROM games WHERE igdb_id = 71").fetchall()]
    for game_id in [*games, *made]:
        c.execute("DELETE FROM game_editions WHERE game_id = ?", game_id)
        c.execute("DELETE FROM games WHERE id = ?", game_id)


def steam_import(client, profile):
    return client.post("/api/collection/steam", json={"profile": profile}, headers=HEADERS)


def test_every_game_goes_in_with_steam_hours_and_achievements(steam):
    client = steam["client"]
    sign_up(client, "ana_steam")
    answer = steam_import(client, "https://steamcommunity.com/id/ana/").get_json()
    assert (answer["total"], answer["added"], answer["updated"]) == (4, 3, 0)
    assert answer["missing"] == [{"name": "Some Tool", "hours": None}]       # IGDB doesn't know it

    items = {i["name"]: i for i in client.get("/api/collection").get_json()["items"]}
    elden = items["Elden Ring"]
    assert (elden["kind"], elden["format"], elden["hours"]) == ("owned", "digital", 100.2)
    assert (elden["achievements"], elden["achievements_total"]) == (12, 42)
    assert items["Portal 2"]["hours"] is None
    assert items["Portal"]["hours"] == 1.5                    # made from IGDB, with its information...
    portal = steam["db"].execute("SELECT summary, created_by FROM games WHERE igdb_id = 71").fetchone()
    assert tuple(portal) == ("Thinking with portals", None)
    catalogue = client.get("/api/games/catalog?q=portal").get_json()["groups"]
    assert catalogue == []                                    # ...but only in the collection


def test_refresh_uses_the_saved_profile_and_updates(steam, monkeypatch):
    client = steam["client"]
    sign_up(client, "rui_steam")
    assert client.get("/api/collection/steam").get_json()["profile"] is None
    assert steam_import(client, "").get_json()["error"] == "steam_profile_invalid"     # nothing saved yet
    steam_import(client, "76561197960287930")                     # an id: no name to resolve
    assert "ISteamUser/ResolveVanityURL/v1/" not in steam["asked"]
    assert client.get("/api/collection/steam").get_json()["profile"]["steam_id"] == "76561197960287930"
    assert steam_import(client, "").get_json()["error"] == "steam_wait"
    steam_service._last.clear()
    assert steam_import(client, "").get_json()["added"] == 0      # already there: nothing twice
    steam_service._last.clear()
    steam["achievements"][1245620] = (13, 42)
    real = steam_service._get
    monkeypatch.setattr(steam_service, "_get", lambda path, **p: {"games": [
        {"appid": 1245620, "name": "ELDEN RING", "playtime_forever": 6100, "has_community_visible_stats": True}]})
    assert steam_import(client, "").get_json()["updated"] == 1    # played since: hours and achievements
    elden = {i["name"]: i for i in client.get("/api/collection").get_json()["items"]}["Elden Ring"]
    assert (elden["hours"], elden["achievements"]) == (101.7, 13)
    monkeypatch.setattr(steam_service, "_get", real)


def test_private_unknown_and_invalid_profiles(steam, monkeypatch):
    client = steam["client"]
    sign_up(client, "eva_steam")
    assert steam_import(client, "https://steamcommunity.com/id/nobody").get_json()["error"] == "steam_profile_not_found"
    assert steam_import(client, "not a profile!").get_json()["error"] == "steam_profile_invalid"
    real = steam_service._get
    monkeypatch.setattr(steam_service, "_get", lambda path, **p: {"steamid": "1", "success": 1} if "Vanity" in path else {})
    assert steam_import(client, "ana").get_json()["error"] == "steam_private"
    monkeypatch.setattr(steam_service, "_get", real)          # made public on Steam: no wait for a failed try
    assert steam_import(client, "ana").get_json()["added"] == 3


def test_importing_needs_a_login(steam):
    assert steam_import(steam["client"], "ana").status_code == 401
