"""Politeness rules of scrapers/base/http_client.py, with a fake session (no network)."""
import pytest

from scrapers.base import http_client
from scrapers.base.http_client import HttpClient, RequestBudgetExceeded, RobotsDisallowed, StoreBlocked


class FakeResponse:
    def __init__(self, status=200, text="", headers=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}
        self.ok = status < 400

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, robots="", responses=None):
        self.robots = robots
        self.responses = responses or {}
        self.requested = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.requested.append(url)
        if url.endswith("/robots.txt"):
            return self.robots if isinstance(self.robots, FakeResponse) else FakeResponse(text=self.robots)
        return self.responses.get(url, FakeResponse(text="ok"))

    def mount(self, *args):
        pass


@pytest.fixture
def clock(monkeypatch):
    """Fake time: sleeping advances the clock instead of waiting."""
    state = {"now": 1000.0, "slept": []}
    monkeypatch.setattr(http_client.time, "monotonic", lambda: state["now"])

    def sleep(seconds):
        state["slept"].append(seconds)
        state["now"] += seconds

    monkeypatch.setattr(http_client.time, "sleep", sleep)
    monkeypatch.setattr(http_client.random, "uniform", lambda a, b: 0)   # no jitter in tests
    return state


def client(session, **kwargs):
    c = HttpClient(**kwargs)
    c.session = session
    return c


def test_waits_between_requests_to_the_same_site(clock):
    c = client(FakeSession())
    c.get_text("https://shop.test/a")
    c.get_text("https://shop.test/b")
    c.get_text("https://shop.test/c")
    assert clock["slept"] == [3.0, 3.0, 3.0]    # robots.txt → a → b → c, 3 s apart


def test_crawl_delay_in_robots_txt_wins_when_larger(clock):
    c = client(FakeSession(robots="User-agent: *\nCrawl-delay: 10"))
    c.get_text("https://shop.test/a")
    c.get_text("https://shop.test/b")
    assert clock["slept"] == [10.0, 10.0]


def test_disallowed_urls_are_never_fetched(clock):
    session = FakeSession(robots="User-agent: *\nDisallow: /checkout")
    c = client(session)
    with pytest.raises(RobotsDisallowed):
        c.get_text("https://shop.test/checkout/1")
    assert "https://shop.test/checkout/1" not in session.requested


def test_robots_txt_refused_means_crawl_nothing(clock):
    c = client(FakeSession(robots=FakeResponse(status=403)))
    with pytest.raises(RobotsDisallowed):
        c.get_text("https://shop.test/a")


def test_missing_robots_txt_allows_everything(clock):
    c = client(FakeSession(robots=FakeResponse(status=404)))
    assert c.get_text("https://shop.test/a") == "ok"


@pytest.mark.parametrize("status", [403, 429])
def test_blocked_stops_immediately(clock, status):
    session = FakeSession(responses={"https://shop.test/a": FakeResponse(status=status, headers={"Retry-After": "120"})})
    with pytest.raises(StoreBlocked, match="Retry-After: 120"):
        client(session).get_text("https://shop.test/a")


def test_request_budget(clock):
    c = client(FakeSession(), max_requests=2)
    c.get_text("https://shop.test/a")
    c.get_text("https://shop.test/b")
    with pytest.raises(RequestBudgetExceeded):
        c.get_text("https://shop.test/c")
    assert c.request_count == 2


def test_release_date_lookups_stop_when_blocked():
    from scrapers.press_start.scraper import PressStartScraper

    calls = []

    def blocked(url):
        calls.append(url)
        raise StoreBlocked("403")

    scraper = PressStartScraper()
    scraper.fetch_release_date = blocked
    products = [{"url": f"https://x/{i}", "is_preorder": True, "release_date": None, "release_date_checked": False}
                for i in range(10)]
    with pytest.raises(StoreBlocked):
        scraper.add_release_dates(products)
    assert len(calls) == 1


def test_release_date_lookups_are_capped_per_run():
    from scrapers.press_start.scraper import PressStartScraper

    scraper = PressStartScraper()
    scraper.max_release_date_lookups = 3
    scraper.fetch_release_date = lambda url: None
    products = [{"url": f"https://x/{i}", "is_preorder": True, "release_date": None, "release_date_checked": False}
                for i in range(10)]
    scraper.add_release_dates(products)
    assert sum(p["release_date_checked"] for p in products) == 3
