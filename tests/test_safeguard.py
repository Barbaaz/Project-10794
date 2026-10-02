"""The half-broken scraper safeguard in scheduler/jobs.py (no database needed)."""
import pytest

from scheduler import jobs


@pytest.mark.parametrize("found, previous, suspicious", [
    (3000, None, False),   # first run: nothing to compare with
    (3000, 3076, False),
    (2200, 3076, False),   # 72%
    (2100, 3076, True),    # 68%
    (10, 3076, True),
])
def test_is_suspicious_drop(found, previous, suspicious):
    assert jobs.is_suspicious_drop(found, previous) is suspicious


class FakeScraper:
    def __init__(self, count):
        self.count = count
        self.http = type("FakeHttp", (), {"request_count": 0})()

    def scrape_catalog(self):
        return [{"url": f"u{i}", "condition": "new", "external_name": f"Game {i} PS5"} for i in range(self.count)]


@pytest.fixture
def run(monkeypatch):
    """run_store with the scraper, database and pipeline replaced by recorders."""
    calls = {}

    def run_store(found, previous, hours_ago=None, **kwargs):
        monkeypatch.setitem(jobs.SCRAPERS, "test_store", lambda **_: FakeScraper(found))
        monkeypatch.setattr(jobs, "fresh_release_urls", lambda slug: set())
        monkeypatch.setattr(jobs, "known_detail_urls", lambda slug: set())
        monkeypatch.setattr(jobs, "hours_since_last_success", lambda slug: hours_ago)
        monkeypatch.setattr(jobs, "start_run", lambda slug: 1)
        monkeypatch.setattr(jobs, "previous_product_count", lambda slug: previous)
        monkeypatch.setattr(jobs, "process_products",
                            lambda slug, products, full_catalog: calls.update(full_catalog=full_catalog) or {})
        monkeypatch.setattr(jobs, "finish_run",
                            lambda run_id, status, **kw: calls.update(status=status, **kw))
        jobs.run_store("test_store", **kwargs)
        return calls

    return run_store


def test_normal_run_deactivates_missing_products(run):
    calls = run(found=3000, previous=3076)
    assert calls["full_catalog"] is True
    assert calls["status"] == "success"


def test_big_drop_saves_prices_but_deactivates_nothing(run):
    calls = run(found=1000, previous=3076)
    assert calls["full_catalog"] is False
    assert calls["status"] == "warning"
    assert "--accept-drop" in calls["error_message"]


def test_accept_drop_deactivates_as_usual(run):
    calls = run(found=1000, previous=3076, accept_drop=True)
    assert calls["full_catalog"] is True
    assert calls["status"] == "success"


def test_zero_products_fails_the_run(run):
    with pytest.raises(RuntimeError):
        run(found=0, previous=3076)


def test_store_scraped_recently_is_not_scraped_again(run):
    with pytest.raises(jobs.RanRecently):
        run(found=3000, previous=3076, hours_ago=2)


def test_force_runs_anyway(run):
    calls = run(found=3000, previous=3076, hours_ago=2, force=True)
    assert calls["status"] == "success"


def test_daily_schedule_is_allowed(run):
    calls = run(found=3000, previous=3076, hours_ago=21)
    assert calls["status"] == "success"
