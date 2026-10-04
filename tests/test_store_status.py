"""Store update status (/api/stores) and the daily-run notification text."""
import pytest

from scheduler.notify import run_summary


@pytest.fixture
def client(app_on_test_db, web_client):
    cursor = app_on_test_db.conn.cursor()
    runs = [
        ("press_start", "success", 2, None),
        ("mega-mania", "success", 50, None),            # no update for 50 h: stale
        ("cstech", "success", 3, None),
        ("cstech", "failed", 1, "cstech.store answered 403"),
    ]
    for slug, status, hours_ago, error in runs:
        cursor.execute(
            "INSERT INTO scrape_runs (store_id, started_at, finished_at, status, error_message) "
            "SELECT id, utcnow() - make_interval(hours => ?), utcnow() - make_interval(hours => ?), ?, ? "
            "FROM stores WHERE slug = ?",
            hours_ago, hours_ago, status, error, slug,
        )
    yield web_client
    cursor.execute("DELETE FROM scrape_runs")


def test_store_status(client, app_on_test_db):
    cursor = app_on_test_db.conn.cursor()
    cursor.execute("UPDATE stores SET is_active = false WHERE slug = 'gaming_replay'")
    try:
        stores = {s["slug"]: s for s in client.get("/api/stores").get_json()}
    finally:
        cursor.execute("UPDATE stores SET is_active = true WHERE slug = 'gaming_replay'")

    assert "gaming_replay" not in stores     # switched off
    assert "radio_popular" in stores
    assert stores["press_start"]["last_status"] == "success"
    assert stores["press_start"]["is_stale"] is False
    assert stores["press_start"]["last_error"] is None

    assert stores["mega-mania"]["is_stale"] is True

    # The latest run failed, but the last success is recent: failed, not stale
    assert stores["cstech"]["last_status"] == "failed"
    assert stores["cstech"]["last_error"] == "cstech.store answered 403"
    assert stores["cstech"]["is_stale"] is False


def test_demo_mode(client, monkeypatch):
    """A test copy on demo data: never stale (a snapshot), and the banner gets the collection date."""
    from app.routes import stores as stores_route

    assert client.get("/api/demo").get_json() == {"demo": False}
    monkeypatch.setattr(stores_route, "DEMO_MODE", True)
    stores = {s["slug"]: s for s in client.get("/api/stores").get_json()}
    assert stores["mega-mania"]["is_stale"] is False
    demo = client.get("/api/demo").get_json()
    assert demo["demo"] is True and demo["collected_at"]


def test_run_summary():
    assert run_summary([], []) is None
    title, message = run_summary(["cstech"], ["mega-mania"])
    assert title == "Game Price Tracker"
    assert "Falhou: cstech" in message and "mega-mania" in message
