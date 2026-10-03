"""Players' reviews of games (on a throwaway database)."""
from helpers import HEADERS, log_in, sign_up


def save(client, game_id, score, title=None, body=None):
    return client.put(f"/api/games/{game_id}/reviews/mine", json={"score": score, "title": title, "body": body},
                      headers=HEADERS)


def reviews(client, game_id):
    return client.get(f"/api/games/{game_id}/reviews").get_json()


def test_one_review_per_user_and_game(market):
    client, game = market["client"], market["game"]
    assert reviews(client, game)["summary"] == {"average": None, "count": 0, "distribution": [0] * 10}
    assert save(client, game, 8).status_code == 401              # logged out

    sign_up(client, "ana")
    page = save(client, game, 8, "  Muito bom  ", "Gostei da história.").get_json()
    assert page["mine"]["score"] == 8 and page["mine"]["title"] == "Muito bom" and not page["mine"]["edited"]
    # changing it updates the same review
    page = save(client, game, 6).get_json()
    assert (page["mine"]["score"], page["mine"]["title"], page["mine"]["edited"]) == (6, None, True)
    assert len(page["reviews"]) == 1 and page["reviews"][0]["mine"]

    sign_up(client, "rui")
    page = save(client, game, 9).get_json()
    assert page["summary"]["average"] == 7.5 and page["summary"]["count"] == 2
    assert page["summary"]["distribution"][5] == 1 and page["summary"]["distribution"][8] == 1
    assert [r["username"] for r in page["reviews"]] == ["rui", "ana"]          # newest first
    # another game (the Switch version, say) has its own reviews
    assert reviews(client, market["other_game"])["summary"]["count"] == 0

    page = client.delete(f"/api/games/{game}/reviews/mine", headers=HEADERS).get_json()
    assert page["mine"] is None and page["summary"]["count"] == 1
    assert client.delete(f"/api/games/{game}/reviews/mine", headers=HEADERS).status_code == 404


def test_review_rules(market):
    client, game = market["client"], market["game"]
    sign_up(client, "ana")
    for score in (0, 11, "x", None):
        assert save(client, game, score).get_json()["error"] == "score_invalid"
    assert save(client, game, 5, "t" * 121).get_json()["error"] == "review_title_long"
    assert save(client, game, 5, body="b" * 4001).get_json()["error"] == "review_text_long"
    assert save(client, 999999, 5).status_code == 404
    assert client.get("/api/games/999999/reviews").status_code == 404


def test_owners_are_marked(market):
    client, game = market["client"], market["game"]
    sign_up(client, "ana")
    client.post("/api/collection", json={"edition_id": market["edition"], "kind": "owned"}, headers=HEADERS)
    save(client, game, 10)
    sign_up(client, "rui")
    save(client, game, 4)
    assert {r["username"]: r["owner"] for r in reviews(client, game)["reviews"]} == {"ana": True, "rui": False}


def test_hidden_reviews_and_blocked_writers_are_not_counted(market):
    client, game, db = market["client"], market["game"], market["db"]
    sign_up(client, "troll")
    review_id = save(client, game, 1, "Lixo").get_json()["mine"]["id"]
    sign_up(client, "ana")
    save(client, game, 9)
    assert client.post("/api/reports", json={"kind": "review", "target_id": review_id, "reason": "offensive"},
                       headers=HEADERS).status_code == 201

    sign_up(client, "mod")
    db.execute("UPDATE users SET role = 'moderator' WHERE username = 'mod'")
    target = client.get("/api/mod/reports").get_json()[0]["target"]
    assert (target["writer"], target["score"], target["title"], target["game"]) == ("troll", 1, "Lixo", "Market Test Game")
    client.post("/api/mod/actions", json={"action": "hide_review", "target_id": review_id}, headers=HEADERS)
    page = reviews(client, game)
    assert page["summary"]["count"] == 1 and [r["username"] for r in page["reviews"]] == ["ana"]

    # its writer still sees it, marked hidden, and can't change or delete it (that would undo the hide)
    log_in(client, "troll")
    assert reviews(client, game)["mine"]["hidden"] is True
    assert save(client, game, 2).get_json()["error"] == "review_hidden"
    assert client.delete(f"/api/games/{game}/reviews/mine", headers=HEADERS).status_code == 403

    log_in(client, "mod")
    client.post("/api/mod/actions", json={"action": "restore_review", "target_id": review_id}, headers=HEADERS)
    assert reviews(client, game)["summary"]["count"] == 2
    # a blocked user's reviews disappear with them
    db.execute("UPDATE users SET is_active = 0 WHERE username = 'troll'")
    assert reviews(client, game)["summary"]["count"] == 1


def test_own_review_cant_be_reported(market):
    client, game = market["client"], market["game"]
    sign_up(client, "ana")
    review_id = save(client, game, 7).get_json()["mine"]["id"]
    response = client.post("/api/reports", json={"kind": "review", "target_id": review_id, "reason": "other"},
                           headers=HEADERS)
    assert response.get_json()["error"] == "report_own"
