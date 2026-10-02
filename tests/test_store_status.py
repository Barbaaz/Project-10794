"""Store update status (/api/stores) and the daily-run notification text."""
import importlib.util

import pytest

from conftest import ROOT
from scheduler.notify import run_summary


@pytest.fixture
def client(app_on_test_db):
    spec = importlib.util.spec_from_file_location("webapp", ROOT / "app.py")
    webapp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(webapp)

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
            "SELECT id, DATEADD(HOUR, ?, SYSUTCDATETIME()), DATEADD(HOUR, ?, SYSUTCDATETIME()), ?, ? "
            "FROM stores WHERE slug = ?",
            -hours_ago, -hours_ago, status, error, slug,
        )
    yield webapp.app.test_client()
    cursor.execute("DELETE FROM scrape_runs")


def test_store_status(client):
    stores = {s["slug"]: s for s in client.get("/api/stores").get_json()}

    assert "gaming_replay" not in stores     # inactive
    assert stores["press_start"]["last_status"] == "success"
    assert stores["press_start"]["is_stale"] is False
    assert stores["press_start"]["last_error"] is None

    assert stores["mega-mania"]["is_stale"] is True

    # The latest run failed, but the last success is recent: failed, not stale
    assert stores["cstech"]["last_status"] == "failed"
    assert stores["cstech"]["last_error"] == "cstech.store answered 403"
    assert stores["cstech"]["is_stale"] is False


def test_run_summary():
    assert run_summary([], []) is None
    title, message = run_summary(["cstech"], ["mega-mania"])
    assert title == "Game Price Tracker"
    assert "Falhou: cstech" in message and "mega-mania" in message
