"""Importing PlayStation games and trophies into the collection, with PSN and IGDB faked; on a throwaway database."""
import pytest

from app.services import igdb_game_service, psn_service
from helpers import HEADERS, sign_up

REAL_GET = psn_service._get


def trophies(bronze, silver, gold, platinum):
    return {"bronze": bronze, "silver": silver, "gold": gold, "platinum": platinum}


@pytest.fixture
def psn(market, monkeypatch):
    """Four games of ours (PS4, PS5), and a fake PSN player with five trophy lists and three played games."""
    c = market["db"]
    platform = lambda code: c.execute("SELECT id FROM platforms WHERE code = ?", code).fetchone()[0]
    games = [c.execute("INSERT INTO games (platform_id, title, normalized_title) VALUES (?, ?, ?) RETURNING id",
                       platform(code), title, key).fetchone()[0]
             for code, title, key in (("PS4", "Bloodborne", "bloodborne"), ("PS5", "Astro Bot", "astro bot"),
                                      ("PS5", "Fortnite", "fortnite"), ("PS5", "Returnal", "returnal"))]
    psn_service._last.clear()
    player = {"lists": [
        {"npCommunicationId": "NPWR00001_00", "trophyTitleName": "Bloodborne™ Trophies", "trophyTitlePlatform": "PS4",
         "definedTrophies": trophies(30, 10, 5, 1), "earnedTrophies": trophies(10, 2, 1, 0)},
        {"npCommunicationId": "NPWR00002_00", "trophyTitleName": "ASTRO BOT", "trophyTitlePlatform": "PS5",
         "definedTrophies": trophies(40, 5, 2, 1), "earnedTrophies": trophies(40, 5, 2, 1)},
        {"npCommunicationId": "NPWR00003_00", "trophyTitleName": "Gravity Rush™", "trophyTitlePlatform": "PSVITA",
         "definedTrophies": trophies(40, 8, 3, 1), "earnedTrophies": trophies(5, 0, 0, 0)},     # IGDB knows it, we don't
        {"npCommunicationId": "NPWR00004_00", "trophyTitleName": "Some Demo", "trophyTitlePlatform": "PS4",
         "definedTrophies": trophies(3, 0, 0, 0), "earnedTrophies": trophies(1, 0, 0, 0)},      # nobody knows it
        {"npCommunicationId": "NPWR00005_00", "trophyTitleName": "A PC Game", "trophyTitlePlatform": "PSPC",
         "definedTrophies": trophies(3, 0, 0, 0), "earnedTrophies": trophies(1, 0, 0, 0)},      # not a console
    ], "played": [
        {"name": "Bloodborne", "category": "ps4_game", "titleId": "CUSA00207_00", "playDuration": "PT50H30M12S",
         "service": "none_purchased"},
        {"name": "Fortnite", "category": "unknown", "titleId": "PPSA01923_00", "playDuration": "PT4H1M",      # no trophy
         "service": "none(purchased)"},                                                                       # list
        {"name": "Returnal", "category": "ps5_native_game", "titleId": "PPSA01284_00", "playDuration": "PT3H",
         "service": "ps_plus"},                                                                               # not theirs
    ], "private": False}
    asked = []

    def fake_get(url, **params):
        asked.append(url)
        if "profile2" in url:
            return (200, {"profile": {"accountId": "4242", "onlineId": "Ana_PS"}}) if "/Ana_PS/" in url else (404, {})
        if "trophyTitles" in url:
            if player["private"]:
                return 403, {"error": {"code": 2240526}}
            page = player["lists"][params["offset"]:params["offset"] + params["limit"]]
            return 200, {"trophyTitles": page, "totalItemCount": len(player["lists"])}
        return 200, {"titles": player["played"], "totalItemCount": len(player["played"])}
    monkeypatch.setattr(psn_service, "_get", fake_get)
    monkeypatch.setattr(psn_service, "query", lambda body, endpoint="games":
                        [{"id": 11701, "name": "Gravity Rush", "platforms": [46]}] if "Gravity Rush" in body else [])
    # IGDB's Gravity Rush, made for the collection only
    monkeypatch.setattr(igdb_game_service, "query", lambda body, endpoint="games":
                        [{"id": 11701, "name": "Gravity Rush", "platforms": [46], "summary": "Falling with style"}])
    yield {**market, "games": games, "player": player, "asked": asked}
    c.execute("DELETE FROM collection_items")
    c.execute("DELETE FROM psn_skips")
    c.execute("UPDATE users SET psn_account_id = NULL, psn_online_id = NULL")
    made = [r[0] for r in c.execute("SELECT id FROM games WHERE igdb_id = 11701").fetchall()]
    for game_id in [*games, *made]:
        c.execute("DELETE FROM game_editions WHERE game_id = ?", game_id)
        c.execute("DELETE FROM games WHERE id = ?", game_id)


def psn_import(client, name):
    return client.post("/api/collection/psn", json={"name": name}, headers=HEADERS)


def items_of(client):
    return {i["name"]: i for i in client.get("/api/collection").get_json()["items"]}


def test_every_game_goes_in_with_trophies_platinum_and_hours(psn):
    client = psn["client"]
    sign_up(client, "ana_psn")
    answer = psn_import(client, "https://profile.playstation.com/Ana_PS").get_json()
    assert (answer["total"], answer["added"], answer["updated"], answer["ps_plus"]) == (5, 4, 0, 1)   # no PC, no PS Plus
    assert answer["missing"] == [{"name": "Some Demo", "platform": "PS4"}]

    items = items_of(client)
    bloodborne, astro, gravity = items["Bloodborne"], items["Astro Bot"], items["Gravity Rush"]
    assert (bloodborne["kind"], bloodborne["format"], bloodborne["hours"]) == ("owned", "digital", 50.5)
    assert (bloodborne["achievements"], bloodborne["achievements_total"], bloodborne["platinum"]) == (13, 46, False)
    assert (astro["achievements"], astro["achievements_total"], astro["platinum"], astro["hours"]) == (48, 48, True, None)
    assert (gravity["platform_name"], gravity["achievements"]) == ("PlayStation Vita", 5)
    fortnite = items["Fortnite"]                               # played, filed as "unknown": a PS5 game by its id
    assert (fortnite["hours"], fortnite["achievements_total"], fortnite["format"]) == (4.0, None, "digital")
    assert "Returnal" not in items
    made = psn["db"].execute("SELECT summary, created_by FROM games WHERE igdb_id = 11701").fetchone()
    assert tuple(made) == ("Falling with style", None)          # only in the collection, as Steam's
    assert client.get("/api/collection/psn").get_json()["profile"]["online_id"] == "Ana_PS"


def test_refresh_uses_the_saved_player_and_updates(psn):
    client = psn["client"]
    sign_up(client, "rui_psn")
    assert client.get("/api/collection/psn").get_json()["profile"] is None
    assert psn_import(client, "").get_json()["error"] == "psn_profile_invalid"       # nothing saved yet
    psn_import(client, "Ana_PS")
    assert psn_import(client, "").get_json()["error"] == "psn_wait"
    psn_service._last.clear()
    again = psn_import(client, "").get_json()
    assert (again["added"], again["updated"]) == (0, 0)                              # nothing twice, nothing changed

    psn_service._last.clear()
    psn["player"]["lists"][0]["earnedTrophies"] = trophies(30, 10, 5, 1)             # the platinum, since
    psn["player"]["played"][0]["playDuration"] = "PT60H"
    assert psn_import(client, "").get_json()["updated"] == 1
    bloodborne = items_of(client)["Bloodborne"]
    assert (bloodborne["achievements"], bloodborne["platinum"], bloodborne["hours"]) == (46, True, 60.0)


def test_hours_only_go_up(psn):
    client = psn["client"]
    sign_up(client, "eva_psn")
    psn_import(client, "Ana_PS")
    bloodborne = items_of(client)["Bloodborne"]
    client.patch(f"/api/collection/{bloodborne['id']}", json={"hours": "80"}, headers=HEADERS)
    psn_service._last.clear()
    psn_import(client, "")
    assert items_of(client)["Bloodborne"]["hours"] == 80.0


def test_private_unknown_and_invalid_players(psn):
    client = psn["client"]
    sign_up(client, "leo_psn")
    assert psn_import(client, "Nobody_Here").get_json()["error"] == "psn_profile_not_found"
    assert psn_import(client, "not a name!").get_json()["error"] == "psn_profile_invalid"
    psn["player"]["private"] = True
    assert psn_import(client, "Ana_PS").get_json()["error"] == "psn_private"
    psn["player"]["private"] = False                       # made public: no wait for a failed try
    assert psn_import(client, "Ana_PS").get_json()["added"] == 4


def test_without_a_token_psn_is_unavailable(psn, monkeypatch):
    client = psn["client"]
    sign_up(client, "no_token")
    monkeypatch.setattr(psn_service, "_get", REAL_GET)     # the real one, with no PSN_NPSSO anywhere
    monkeypatch.delenv("PSN_NPSSO", raising=False)
    monkeypatch.setattr(psn_service.sys, "platform", "linux")
    psn_service._token.update(access=None, refresh=None)
    answer = psn_import(client, "Ana_PS")
    assert (answer.status_code, answer.get_json()["error"]) == (503, "psn_unavailable")


def test_importing_needs_a_login(psn):
    assert psn_import(psn["client"], "Ana_PS").status_code == 401


def test_a_game_taken_out_is_not_imported_again(psn):
    """PSN's trophy lists also have games played on PS Plus: the user takes them out once and imports
    leave them out; adding one by hand brings it back."""
    client = psn["client"]
    sign_up(client, "ps_plus")
    psn_import(client, "Ana_PS")
    astro = items_of(client)["Astro Bot"]
    removed = client.delete(f"/api/collection/{astro['id']}", headers=HEADERS).get_json()
    assert removed == {"ok": True, "steam_skipped": False, "psn_skipped": True}
    psn_service._last.clear()
    answer = psn_import(client, "").get_json()
    assert (answer["added"], answer["skipped"]) == (0, 1)
    assert "Astro Bot" not in items_of(client)
    assert client.get("/api/auth/export").get_json()["psn_skipped_lists"] == ["NPWR00002_00"]   # their data (GDPR)

    client.post("/api/collection", json={"edition_id": astro["edition_id"], "kind": "owned"}, headers=HEADERS)
    psn_service._last.clear()
    answer = psn_import(client, "").get_json()
    assert (answer["skipped"], answer["updated"]) == (0, 1)        # wanted again: its trophies come back
    assert items_of(client)["Astro Bot"]["platinum"] is True


def test_the_platinum_can_be_ticked_by_hand(psn):
    client = psn["client"]
    sign_up(client, "by_hand")
    edition = psn["db"].execute("SELECT id FROM game_editions WHERE game_id = ?", psn["games"][0]).fetchone()
    if edition is None:
        edition = psn["db"].execute("INSERT INTO game_editions (game_id, edition_key, name) VALUES (?, '', 'Standard') "
                                    "RETURNING id", psn["games"][0]).fetchone()
    item_id = client.post("/api/collection", json={"edition_id": edition[0], "kind": "owned"}, headers=HEADERS).get_json()["id"]
    client.patch(f"/api/collection/{item_id}", json={"platinum": True}, headers=HEADERS)
    assert items_of(client)["Bloodborne"]["platinum"] is True


def test_trophy_list_names_become_game_names():
    assert psn_service.clean("Uncharted™: Drake's Fortune Trophies") == "Uncharted: Drake's Fortune"
    assert psn_service.clean("Gran Turismo® 7") == "Gran Turismo 7"
    assert psn_service.clean("Crash Bandicoot (PS4)") == "Crash Bandicoot"
    assert psn_service.online_id("https://psnprofiles.com/Ana_PS/") == "Ana_PS"
    assert psn_service.clean("ASTRO’s PLAYROOM") == "ASTRO's PLAYROOM"
    assert psn_service.clean("DARK SOULS™ Ⅱ") == "DARK SOULS II"        # not "DARK SOULSTM II"
    assert psn_service.words("Devil May Cry 4 Special Edition") == psn_service.words("Devil May Cry 4: Special Edition")


def test_igdb_search_takes_only_the_same_words(monkeypatch):
    """Names IGDB doesn't have as they are: its search, when the words are the same but for editions'."""
    games = {"Killzone": [{"id": 1, "name": "Killzone: Shadow Fall", "platforms": [48]}],
             "Overcooked": [{"id": 2, "name": "Overcooked! 2", "platforms": [48]}],
             "Control": [{"id": 3, "name": "Control", "platforms": [167]}]}
    monkeypatch.setattr(psn_service, "query", lambda body, endpoint="games": [] if body.startswith("fields") else
                        next((g for k, g in games.items() if f'search "{k}' in body), []))
    lists = [{"id": "A", "name": "Killzone Shadow Fall", "platforms": ["PS4"]},
             {"id": "B", "name": "Overcooked", "platforms": ["PS4"]},
             {"id": "C", "name": "Control Ultimate Edition", "platforms": ["PS5"]}]
    assert psn_service.igdb_games(lists) == {"A": (1, "PS4"), "C": (3, "PS5")}


def test_ps_plus_games_only_when_asked(psn):
    """Games only played on PS Plus aren't the player's: out unless they ask; bought after PS Plus: theirs."""
    client = psn["client"]
    sign_up(client, "plus_psn")
    answer = client.post("/api/collection/psn", json={"name": "Ana_PS", "ps_plus": True}, headers=HEADERS).get_json()
    assert (answer["added"], answer["ps_plus"]) == (5, 0)
    assert items_of(client)["Returnal"]["hours"] == 3.0

    psn_service._last.clear()
    client.delete(f"/api/collection/{items_of(client)['Returnal']['id']}", headers=HEADERS)
    psn["player"]["played"].append({"name": "Returnal", "category": "ps5_native_game", "titleId": "PPSA01285_00",
                                    "playDuration": "PT1H", "service": "none_purchased"})      # bought, another region
    client.post("/api/collection/psn", json={}, headers=HEADERS)
    assert "Returnal" not in items_of(client)                  # taken out: not again, however it was played


def test_a_game_taken_out_stays_out_whatever_brings_it(psn):
    """A trophy list and a played game of another name, both the same game: taking it out skips both."""
    client = psn["client"]
    sign_up(client, "two_names")
    psn["player"]["played"].append({"name": "Bloodborne (PS4)", "category": "ps4_game", "titleId": "CUSA00900_00",
                                    "playDuration": "PT2H", "service": "none_purchased"})
    psn["player"]["played"][0]["name"] = "Bloodborne Game of the Year"      # matched to the list by edition only
    psn_import(client, "Ana_PS")
    client.delete(f"/api/collection/{items_of(client)['Bloodborne']['id']}", headers=HEADERS)
    psn_service._last.clear()
    psn_import(client, "")
    assert "Bloodborne" not in items_of(client)
