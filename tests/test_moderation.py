"""Reports and the moderators' tools (on a throwaway database)."""
from helpers import HEADERS, completed_purchase, log_in, new_listing, sign_up


def make(m, username, role):
    m["db"].execute("UPDATE users SET role = ? WHERE username = ?", role, username)


def report(client, kind, target_id, reason="scam", details=None):
    return client.post("/api/reports", json={"kind": kind, "target_id": target_id, "reason": reason,
                                             "details": details}, headers=HEADERS)


def act(client, action, target_id, note=None):
    return client.post("/api/mod/actions", json={"action": action, "target_id": target_id, "note": note},
                       headers=HEADERS)


def user_id(m, username):
    return m["db"].execute("SELECT id FROM users WHERE username = ?", username).fetchone()[0]


def test_reporting_rules(market):
    client = market["client"]
    assert report(client, "listing", 1).status_code == 401            # needs an account
    seller = sign_up(client, "seller")
    listing = new_listing(market).get_json()
    assert report(client, "listing", listing["id"]).get_json()["error"] == "report_own"
    assert report(client, "user", seller["id"]).get_json()["error"] == "report_own"

    sign_up(client, "reporter")
    assert report(client, "game", listing["id"]).get_json()["error"] == "report_kind_invalid"
    assert report(client, "listing", listing["id"], reason="ugly").get_json()["error"] == "report_reason_invalid"
    assert report(client, "listing", listing["id"], details="x" * 1001).get_json()["error"] == "details_long"
    assert report(client, "listing", 999999).status_code == 404
    assert report(client, "listing", "abc").status_code == 404

    assert report(client, "listing", listing["id"], details="  Fotos tiradas da internet.  ").status_code == 201
    assert report(client, "listing", listing["id"]).status_code == 409     # already reported, still open
    assert report(client, "user", seller["id"], reason="offensive").status_code == 201
    assert market["db"].execute("SELECT details FROM reports WHERE kind = 'listing'").fetchone()[0] \
        == "Fotos tiradas da internet."


def test_daily_report_limit(market):
    client = market["client"]
    seller = sign_up(client, "seller")
    listing = new_listing(market).get_json()
    reporter = sign_up(client, "reporter")
    for n in range(20):                                   # 20 reports in the last day (since closed)
        market["db"].execute("INSERT INTO reports (reporter_id, kind, target_id, reason, status) "
                             "VALUES (?, 'user', ?, 'other', 'dismissed')", reporter["id"], seller["id"])
    assert report(client, "listing", listing["id"]).status_code == 429
    market["db"].execute("UPDATE reports SET created_at = DATEADD(DAY, -2, created_at)")
    assert report(client, "listing", listing["id"]).status_code == 201


def test_only_moderators_see_the_tools(market):
    client = market["client"]
    assert client.get("/api/mod/reports").status_code == 401
    sign_up(client, "someone")
    for path in ("/api/mod/reports", "/api/mod/problems", "/api/mod/log", "/api/mod/staff"):
        assert client.get(path).status_code == 403
    assert act(client, "dismiss", 1).status_code == 403

    assert client.get("/admin").status_code == 200          # the page itself; its data is what's guarded
    make(market, "someone", "moderator")
    assert client.get("/api/mod/reports").status_code == 200
    assert client.get("/api/mod/staff").status_code == 403             # admins only
    make(market, "someone", "admin")
    assert client.get("/api/mod/staff").get_json() == [{"id": user_id(market, "someone"), "username": "someone",
                                                         "role": "admin"}]


def test_hiding_a_listing(market):
    client = market["client"]
    sign_up(client, "seller")
    listing = new_listing(market).get_json()
    for reporter in ("reporter1", "reporter2"):
        sign_up(client, reporter)
        report(client, "listing", listing["id"], reason="fake")

    sign_up(client, "mod")
    make(market, "mod", "moderator")
    reports = client.get("/api/mod/reports").get_json()
    assert len(reports) == 1 and len(reports[0]["reports"]) == 2
    assert reports[0]["target"]["seller"] == "seller" and reports[0]["target"]["title"] == "Market Test Game"

    assert act(client, "hide_listing", listing["id"], "Fotos falsas.").get_json() == {"ok": True}
    assert client.get("/api/mod/reports").get_json() == []                # both reports resolved
    log = client.get("/api/mod/log").get_json()
    assert (log[0]["action"], log[0]["moderator"], log[0]["note"]) == ("hide_listing", "mod", "Fotos falsas.")

    log_in(client, "reporter1")
    assert client.get(f"/api/listings/{listing['id']}").status_code == 404
    assert client.get("/api/listings").get_json()["groups"] == []

    # the seller can't put it back up; a moderator can
    log_in(client, "seller")
    assert client.get(f"/api/listings/{listing['id']}").get_json()["removed_by_moderator"] is True
    changed = client.patch(f"/api/listings/{listing['id']}", json={"status": "active"}, headers=HEADERS)
    assert (changed.status_code, changed.get_json()["error"]) == (403, "removed_by_moderator")
    log_in(client, "mod")
    act(client, "restore_listing", listing["id"])
    log_in(client, "reporter1")
    assert client.get(f"/api/listings/{listing['id']}").status_code == 200


def test_restoring_a_sold_listing_keeps_it_sold(market):
    client = market["client"]
    conversation_id = completed_purchase(market)
    listing_id = market["db"].execute("SELECT listing_id FROM conversations WHERE id = ?", conversation_id).fetchone()[0]
    sign_up(client, "mod")
    make(market, "mod", "moderator")
    act(client, "hide_listing", listing_id)
    act(client, "restore_listing", listing_id)
    assert market["db"].execute("SELECT status FROM user_listings WHERE id = ?", listing_id).fetchone()[0] == "sold"


def test_hiding_a_rating(market):
    client = market["client"]
    conversation_id = completed_purchase(market)
    rating = client.post(f"/api/conversations/{conversation_id}/rating", json={"stars": 1, "comment": "Insulto."},
                         headers=HEADERS).get_json()["mine"]
    log_in(client, "seller")
    assert report(client, "rating", rating["id"], reason="offensive").status_code == 201

    sign_up(client, "mod")
    make(market, "mod", "moderator")
    target = client.get("/api/mod/reports").get_json()[0]["target"]
    assert (target["rater"], target["rated"], target["comment"]) == ("buyer", "seller", "Insulto.")
    act(client, "hide_rating", rating["id"])
    profile = client.get("/api/users/seller").get_json()
    assert (profile["rating_count"], profile["ratings"]) == (0, [])
    act(client, "restore_rating", rating["id"])
    assert client.get("/api/users/seller").get_json()["rating_count"] == 1


def test_blocking_a_user(market):
    client = market["client"]
    seller = sign_up(client, "seller")
    listing = new_listing(market).get_json()

    seller_browser = client.application.test_client()
    log_in(seller_browser, "seller")

    sign_up(client, "mod")
    make(market, "mod", "moderator")
    assert act(client, "block_user", seller["id"]).status_code == 200
    assert client.get(f"/api/listings/{listing['id']}").status_code == 404
    assert client.get("/api/users/seller").status_code == 404

    # logged out on their next request, and can't log in again
    assert seller_browser.get("/api/auth/me").get_json() is None
    assert seller_browser.post("/api/auth/login", headers=HEADERS,
                               json={"login": "seller", "password": "segredo123"}).status_code == 400

    act(client, "unblock_user", seller["id"])
    assert client.get(f"/api/listings/{listing['id']}").status_code == 200
    log_in(seller_browser, "seller")


def test_who_may_block_whom(market):
    client = market["client"]
    for name in ("admin", "mod_a", "mod_b"):
        sign_up(client, name)
    make(market, "admin", "admin")
    make(market, "mod_a", "moderator")
    make(market, "mod_b", "moderator")
    admin, mod_a, mod_b = (user_id(market, n) for n in ("admin", "mod_a", "mod_b"))

    log_in(client, "mod_a")
    for target in (mod_a, mod_b, admin):                                   # themselves, a moderator, an admin
        assert act(client, "block_user", target).status_code == 403
    log_in(client, "admin")
    assert act(client, "block_user", admin).status_code == 403
    assert act(client, "block_user", mod_b).status_code == 200            # an admin may block a moderator
    assert act(client, "fly", mod_b).get_json()["error"] == "action_invalid"
    assert act(client, "hide_listing", 999999).status_code == 404


def test_dismissing_a_report(market):
    client = market["client"]
    seller = sign_up(client, "seller")
    sign_up(client, "reporter")
    report(client, "user", seller["id"], reason="other", details="Não gosto do nome.")
    sign_up(client, "mod")
    make(market, "mod", "moderator")
    report_id = client.get("/api/mod/reports").get_json()[0]["reports"][0]["id"]
    assert act(client, "dismiss", report_id, "Sem motivo.").status_code == 200
    assert act(client, "dismiss", report_id).status_code == 404            # no longer open
    assert client.get("/api/mod/reports").get_json() == []
    assert market["db"].execute("SELECT status FROM reports WHERE id = ?", report_id).fetchone()[0] == "dismissed"
    # the reporter may report it again later
    log_in(client, "reporter")
    assert report(client, "user", seller["id"]).status_code == 201


def test_problem_purchases(market):
    client = market["client"]
    sign_up(client, "seller")
    listing = new_listing(market).get_json()
    sign_up(client, "buyer")
    step = lambda cid, action: client.post(f"/api/conversations/{cid}/steps", json={"action": action}, headers=HEADERS)
    conversation_id = client.post(f"/api/listings/{listing['id']}/conversation", json={"buy": True},
                                  headers=HEADERS).get_json()["id"]
    log_in(client, "seller")
    step(conversation_id, "accept")
    step(conversation_id, "sent")
    log_in(client, "buyer")
    step(conversation_id, "problem")

    sign_up(client, "mod")
    make(market, "mod", "moderator")
    problems = client.get("/api/mod/problems").get_json()
    assert [(p["id"], p["buyer"], p["seller"]) for p in problems] == [(conversation_id, "buyer", "seller")]
    messages = client.get(f"/api/mod/conversations/{conversation_id}").get_json()
    assert messages["deal_status"] == "problem" and messages["messages"]
    assert client.get("/api/mod/conversations/999999").status_code == 404


def test_admins_name_moderators(market):
    client = market["client"]
    sign_up(client, "helper")
    sign_up(client, "boss")
    make(market, "boss", "admin")
    post = lambda username, role: client.post("/api/mod/staff", json={"username": username, "role": role},
                                              headers=HEADERS)
    assert [u["username"] for u in post("helper", "moderator").get_json()] == ["boss", "helper"]
    assert post("helper", "admin").get_json()["error"] == "role_invalid"   # admins: command line only
    assert post("boss", "user").status_code == 403
    assert post("nobody", "moderator").status_code == 404
    assert [u["username"] for u in post("helper", "user").get_json()] == ["boss"]
    assert client.get("/api/mod/log").get_json()[0]["action"] == "role_user"
