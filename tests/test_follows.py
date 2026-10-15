"""Following users and comparing collections (user, 2026-10-12; on a throwaway database)."""
from helpers import HEADERS, log_in, sign_up


def add(client, edition_id, **fields):
    return client.post("/api/collection", json={"edition_id": edition_id, "kind": "owned", **fields}, headers=HEADERS)


def item_id(client, edition_id, format="physical"):
    return next(i["id"] for i in client.get("/api/collection").get_json()["items"]
                if i["edition_id"] == edition_id and i["format"] == format)


def test_follow_and_unfollow(market):
    client = market["client"]
    sign_up(client, "rita")
    sign_up(client, "tiago")                                         # logged in as tiago
    assert client.post("/api/users/rita/follow", headers=HEADERS).get_json() == {"following": True}
    client.post("/api/users/RITA/follow", headers=HEADERS)            # twice, any case: once
    assert client.get("/api/users/rita/follows").get_json() == {"followers": 1, "following": 0, "followed": True}
    assert client.get("/api/following").get_json() == [{"username": "rita", "display_name": "rita", "avatar": None,
                                                         "collection_public": False}]
    answer = client.post("/api/users/tiago/follow", headers=HEADERS)
    assert (answer.status_code, answer.get_json()["error"]) == (400, "follow_self")
    assert client.post("/api/users/nobody/follow", headers=HEADERS).status_code == 404

    log_in(client, "rita")                                            # who tiago follows is his to see
    assert client.get("/api/following").get_json() == []
    assert client.get("/api/users/tiago/follows").get_json() == {"followers": 0, "following": 1, "followed": False}
    log_in(client, "tiago")
    assert client.delete("/api/users/rita/follow", headers=HEADERS).get_json() == {"following": False}
    assert client.get("/api/users/rita/follows").get_json()["followers"] == 0


def test_following_needs_a_login(market):
    client = market["client"]
    assert client.post("/api/users/rita/follow", headers=HEADERS).status_code == 401
    assert client.get("/api/following").status_code == 401
    assert client.get("/api/users/rita/compare").status_code == 401


def test_compare_collections(market):
    """Games both have (one game across platforms and copies), the ones only one has; hours, trophies."""
    from app.services import collection_service     # trophies only come from the imports, which write them so
    client = market["client"]
    ana = sign_up(client, "ana_c")["id"]
    add(client, market["edition"], hours="10")
    collection_service.update(ana, item_id(client, market["edition"]), {"achievements": 5, "achievements_total": 50})
    add(client, market["edition"], format="digital", hours="2,5")                  # the same game, a download
    add(client, market["other_edition"], status="finished")
    rui = sign_up(client, "rui_c")["id"]
    add(client, market["edition"], hours="40")
    collection_service.update(rui, item_id(client, market["edition"]), {"achievements": 50, "achievements_total": 50, "platinum": True})
    answer = client.get("/api/users/ana_c/compare")
    assert (answer.status_code, answer.get_json()["error"]) == (403, "collection_private")

    log_in(client, "ana_c")
    client.put("/api/collection/settings", json={"public": True}, headers=HEADERS)
    log_in(client, "rui_c")
    data = client.get("/api/users/ana_c/compare").get_json()
    assert (data["me"]["username"], data["them"]["username"]) == ("rui_c", "ana_c")
    [both] = data["both"]
    assert both["name"] == "Market Test Game"
    assert (both["me"]["hours"], both["me"]["achievements"], both["me"]["platinum"]) == (40.0, 50, True)
    assert (both["them"]["hours"], both["them"]["achievements"], both["them"]["achievements_total"]) == (12.5, 5, 50)
    assert [g["name"] for g in data["only_them"]] == ["Other Game"] and data["only_me"] == []
    assert data["them"]["summary"] == {"games": 2, "finished": 1, "hours": 12.5, "achievements": 5,
                                       "achievements_total": 50, "platinums": 0}
    assert data["me"]["summary"]["platinums"] == 1


def test_a_deleted_account_leaves_no_follows(market):
    client = market["client"]
    sign_up(client, "leaving")
    sign_up(client, "staying")
    client.post("/api/users/leaving/follow", headers=HEADERS)
    log_in(client, "leaving")
    client.post("/api/users/staying/follow", headers=HEADERS)
    assert client.get("/api/auth/export").get_json()["following"] == ["staying"]
    client.post("/api/auth/delete", json={"password": "segredo123"}, headers=HEADERS)
    log_in(client, "staying")
    assert client.get("/api/following").get_json() == []
    assert market["db"].execute("SELECT count(*) FROM follows").fetchone()[0] == 0
