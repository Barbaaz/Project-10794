"""Owned DLC in the collection (user, 2026-10-13; app/services/dlc_service.py; IGDB replaced)."""
import re

import pytest

from helpers import HEADERS, sign_up
from app.services import dlc_service

WITCHER = {"id": 1942, "name": "Witcher 3", "game_type": 0,
           "dlcs": [{"id": 501, "name": "Witcher 3 - New Quest 'Fool's Gold'", "first_release_date": 1433116800,
                     "cover": {"image_id": "cofg"}}],
           "expansions": [{"id": 502, "name": "Witcher 3 - Blood and Wine", "first_release_date": 1464048000},
                          {"id": 503, "name": "Witcher 3 - Hearts of Stone", "first_release_date": 1444694400}]}
REMASTER = {"id": 7000, "game_type": 9, "version_parent": 1942}          # listed without add-ons: the original's


@pytest.fixture
def dlc(market, monkeypatch):
    asked = []

    def query(body):
        asked.append(body)
        ids = {int(i) for i in re.search(r"where id = \(([\d,]+)\)", body).group(1).split(",")}
        return [g for g in (WITCHER, REMASTER, {"id": 8000, "game_type": 0}) if g["id"] in ids]
    monkeypatch.setattr(dlc_service, "query", query)
    c = market["db"]
    c.execute("UPDATE games SET igdb_id = 1942 WHERE id = ?", market["game"])
    yield market | {"asked": asked}
    c.execute("DELETE FROM igdb_addons")
    c.execute("UPDATE games SET igdb_id = NULL WHERE id IN (?, ?)", market["game"], market["other_game"])


def test_ticking_the_dlc_a_game_has(dlc):
    client = dlc["client"]
    sign_up(client, "dlc_owner")
    item = client.post("/api/collection", json={"edition_id": dlc["edition"], "kind": "owned"}, headers=HEADERS).get_json()["id"]

    listed = client.get(f"/api/collection/{item}/dlc").get_json()
    assert [(a["igdb_id"], a["type"], a["year"]) for a in listed["addons"]] == [
        (501, "dlc", 2015), (503, "expansion", 2015), (502, "expansion", 2016)]          # oldest first
    assert listed["addons"][0]["cover"].endswith("/t_cover_small/cofg.jpg") and listed["owned"] == []
    assert [a["name"] for a in listed["addons"]] == ["New Quest 'Fool's Gold'", "Hearts of Stone", "Blood and Wine"]
    client.get(f"/api/collection/{item}/dlc")
    assert len(dlc["asked"]) == 1                                                        # kept, not asked again

    put = lambda owned: client.put(f"/api/collection/{item}/dlc", json={"owned": owned}, headers=HEADERS)
    assert put([502, 503]).get_json() == {"owned": 2, "total": 3}
    assert put([999]).get_json()["error"] == "dlc_invalid"                               # not this game's
    assert put(["502"]).status_code == 400
    assert client.get(f"/api/collection/{item}/dlc").get_json()["owned"] == [503, 502]
    assert client.get("/api/collection").get_json()["items"][0]["dlc"] == {"owned": 2, "total": 3}

    # someone else's item, a wish, a game without IGDB
    other = client.post("/api/collection", json={"edition_id": dlc["other_edition"], "kind": "wishlist"}, headers=HEADERS)
    assert client.get(f"/api/collection/{other.get_json()['id']}/dlc").get_json()["error"] == "dlc_owned_only"
    client.post("/api/auth/logout", headers=HEADERS)
    sign_up(client, "dlc_stranger")
    assert client.get(f"/api/collection/{item}/dlc").status_code == 404
    assert put([502]).status_code == 404


def test_a_remaster_without_addons_takes_its_originals(dlc):
    lists = dlc_service.refresh([7000, 8000])
    assert [a["igdb_id"] for a in lists[7000]] == [501, 503, 502]
    assert lists[8000] == []                                         # none: kept as none, not asked again
    assert dlc_service.kept([7000, 8000], fresh_only=True).keys() == {7000, 8000}


def test_the_daily_run_fetches_owned_games_lists(dlc):
    client = dlc["client"]
    sign_up(client, "dlc_daily")
    client.post("/api/collection", json={"edition_id": dlc["edition"], "kind": "owned"}, headers=HEADERS)
    assert dlc_service.refresh_collection_games() == 1
    assert dlc_service.refresh_collection_games() == 0                # fresh: left until KEEP_DAYS
