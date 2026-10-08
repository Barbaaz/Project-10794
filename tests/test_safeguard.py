"""The half-broken scraper safeguard in scheduler/jobs.py (no database needed, except the lock test)."""
from contextlib import nullcontext

import pytest

import db
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

    def run_store(found, previous, hours_ago=None, blocked_ago=None, **kwargs):
        monkeypatch.setitem(jobs.SCRAPERS, "test_store", lambda **_: FakeScraper(found))
        monkeypatch.setattr(jobs, "fresh_release_urls", lambda slug: set())
        monkeypatch.setattr(jobs, "known_detail_urls", lambda slug: set())
        monkeypatch.setattr(jobs, "store_lock", lambda slug: nullcontext())
        monkeypatch.setattr(jobs, "hours_since_last_success", lambda slug: hours_ago)
        monkeypatch.setattr(jobs, "hours_since_blocked", lambda slug: blocked_ago)
        monkeypatch.setattr(jobs, "start_run", lambda slug: 1)
        monkeypatch.setattr(jobs, "previous_product_count", lambda slug: previous)
        monkeypatch.setattr(jobs, "process_products",
                            lambda slug, products, full_catalog, **_: calls.update(full_catalog=full_catalog) or {})
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


def test_a_store_that_refused_us_is_left_alone_for_a_day(run):
    with pytest.raises(jobs.Paused):
        run(found=3000, previous=3076, hours_ago=30, blocked_ago=3)
    assert run(found=3000, previous=3076, hours_ago=30, blocked_ago=25)["status"] == "success"
    assert run(found=3000, previous=3076, hours_ago=30, blocked_ago=3, force=True)["status"] == "success"


def test_a_403_or_429_is_recorded_as_blocked(monkeypatch):
    def refuse(**_):
        scraper = FakeScraper(1)
        scraper.scrape_catalog = lambda: (_ for _ in ()).throw(jobs.StoreBlocked("shop.test answered 429"))
        return scraper

    monkeypatch.setitem(jobs.SCRAPERS, "refusing", refuse)
    calls = {}
    for name, value in {"fresh_release_urls": lambda s: set(), "known_detail_urls": lambda s: set(),
                        "last_seen": lambda s: {}, "store_lock": lambda s: nullcontext(),
                        "hours_since_last_success": lambda s: None, "hours_since_blocked": lambda s: None,
                        "start_run": lambda s: 1,
                        "finish_run": lambda run_id, status, **kw: calls.update(status=status, **kw)}.items():
        monkeypatch.setattr(jobs, name, value)
    with pytest.raises(jobs.StoreBlocked):
        jobs.run_store("refusing")
    assert calls == {"status": "failed", "error_message": "Blocked: shop.test answered 429"}


def test_blocked_and_last_run_hours_from_the_database(test_db, monkeypatch):
    """hours_since_blocked: only when the latest run was refused; hours_since_last_run: any outcome."""
    monkeypatch.setattr(db, "DB_CONNECTION_STRING", test_db.url)
    cur = test_db.conn.cursor()
    ids = [cur.execute("INSERT INTO stores (slug, name, base_url, is_active) VALUES (?, ?, ?, false) RETURNING id",
                       slug, slug, "https://shop.test").fetchone()[0] for slug in ("pause_a", "pause_b")]
    try:
        def add_run(store, hours_ago, status, message=None):
            cur.execute("INSERT INTO scrape_runs (store_id, started_at, finished_at, status, error_message) "
                        "VALUES (?, utcnow() - make_interval(hours => ?), utcnow() - make_interval(hours => ?), ?, ?)",
                        store, hours_ago, hours_ago, status, message)

        add_run(ids[0], 30, "success")
        add_run(ids[0], 3, "failed", "Blocked: shop.test answered 429")
        add_run(ids[1], 5, "failed", "Blocked: shop.test answered 403")
        add_run(ids[1], 2, "success")
        assert 2.9 < jobs.hours_since_blocked("pause_a") < 3.1
        assert jobs.hours_since_blocked("pause_b") is None          # it worked again since
        assert 1.9 < jobs.hours_since_last_run(["pause_a", "pause_b"]) < 2.1
        assert jobs.hours_since_last_run(["no_such_store"]) is None
    finally:
        cur.execute("DELETE FROM scrape_runs WHERE store_id = ANY(?)", [ids])
        cur.execute("DELETE FROM stores WHERE id = ANY(?)", [ids])


def test_a_store_is_scraped_by_one_run_at_a_time(test_db, monkeypatch):
    """Another process can't take the store's lock while a run holds it; other stores are free."""
    monkeypatch.setattr(db, "DB_CONNECTION_STRING", test_db.url)

    def free(slug):
        other = db.connect(test_db.url, autocommit=True)
        try:
            cursor = other.cursor()
            taken = cursor.execute("SELECT pg_try_advisory_lock(hashtext(?))", f"scrape_store:{slug}").fetchone()[0]
            if taken:
                cursor.execute("SELECT pg_advisory_unlock(hashtext(?))", f"scrape_store:{slug}")
            return taken
        finally:
            other.close()

    with jobs.store_lock("cstech"):
        assert not free("cstech")
        assert free("press_start")
    assert free("cstech")


def test_a_store_not_switched_on_writes_its_hardware_check(tmp_path, monkeypatch):
    """CSTech's feed sorts its hardware without saving it: the names go to logs/hardware_check_<store>.txt."""
    monkeypatch.setattr(jobs, "LOG_DIR", tmp_path)
    kept = [{"kind": "controller", "console": "PS5", "condition": "new", "price": 69.99, "external_name": "Comando DualSense"}]
    jobs.write_hardware_check("cstech", kept, ["Cabo USB-C", "Cabo USB-C"])
    assert (tmp_path / "hardware_check_cstech.txt").read_text(encoding="utf-8").splitlines() == [
        "KEPT (1)", "controller PS5        new  69.99 | Comando DualSense", "", "LEFT OUT (2)", "Cabo USB-C"]
