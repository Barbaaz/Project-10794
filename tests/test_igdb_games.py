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
    c.execute("DELETE FROM listing_photos WHERE listing_id IN (SELECT id FROM user_listings WHERE game_id IN "
              "(SELECT id FROM games WHERE igdb_id = 9001))")
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


def test_search_words_stay_inside_the_query_text(igdb):
    """A typed backslash would escape the closing quote of IGDB's search "…": it goes, like quotes."""
    client = igdb["client"]
    sign_up(client, "retro_seller3")
    client.get('/api/igdb/games?q=okami \\" ; fields *; \\')
    search = igdb["asked"][-1]
    assert search.startswith('search "okami ; fields *;"; fields ')
    assert "\\" not in search


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


# Okami's versions on IGDB (version_parent = 9001), as the edition list asks for them
OKAMI_VERSIONS = [
    {"version_title": "Collector's Edition", "platforms": [8]},
    {"version_title": "Digital Deluxe Edition", "platforms": [8]},           # downloads only: no
    {"version_title": "Wii Limited Edition", "platforms": [5]},              # another platform: no
    {"version_title": "Steelbook Edition"},                                  # no platforms listed: offered
    {"version_title": "Standard Edition", "platforms": [8]},                 # we have it (Standard)
]


def test_a_listing_can_be_for_one_of_the_games_igdb_editions(igdb, monkeypatch):
    """The seller picks an edition IGDB knows (never types one); it's created with the listing."""
    from helpers import new_listing

    plain = igdb_game_service.query
    monkeypatch.setattr(igdb_game_service, "query",
                        lambda body: OKAMI_VERSIONS if "version_parent = 9001" in body else plain(body))
    client = igdb["client"]
    sign_up(client, "retro_seller4")
    made = client.post("/api/igdb/games", headers=HEADERS, json={"igdb_id": 9001, "platform": "PS2"}).get_json()
    options = client.get(f"/api/igdb/games/{made['game_id']}/editions").get_json()
    assert options == ["Collector's Edition", "Steelbook Edition"]

    sold = new_listing(igdb, game_id=made["game_id"], edition_id="", new_edition="Collector's Edition")
    assert sold.status_code == 201
    editions = {e["name"]: e["id"] for e in client.get(f"/api/games/{made['game_id']}").get_json()["editions"]}
    assert sold.get_json()["edition_id"] == editions["Collector's Edition"]
    assert client.get(f"/api/igdb/games/{made['game_id']}/editions").get_json() == ["Steelbook Edition"]
    # a second copy of that edition goes to the same edition, not a new one
    again = new_listing(igdb, game_id=made["game_id"], edition_id="", new_edition="Steelbook Edition")
    assert again.status_code == 201
    # a name of the seller's own, or IGDB's for a digital version: refused
    for name in ("Edição do Paulo", "Digital Deluxe Edition"):
        refused = new_listing(igdb, game_id=made["game_id"], edition_id="", new_edition=name)
        assert (refused.status_code, refused.get_json()["error"]) == (400, "edition_invalid")


def test_no_igdb_editions_without_an_igdb_match(igdb):
    client = igdb["client"]
    sign_up(client, "retro_seller5")
    assert client.get(f"/api/igdb/games/{igdb['game']}/editions").get_json() == []     # the market game has no IGDB id
