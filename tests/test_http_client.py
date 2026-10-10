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

    def request(self, method, url, params=None, data=None, headers=None, timeout=None):
        self.methods = getattr(self, "methods", []) + [method]
        return self.get(url, params, timeout)

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


def test_robots_txt_wildcards():
    """Rules with * and $ (Techinn's, xtralife's): Python's own parser read them as allowed."""
    from scrapers.base.robots import RobotsRules

    robots = RobotsRules.parse("\n".join([
        "User-agent: *",
        "Disallow: *query=*", "Disallow: */ofertas*", "Disallow: */cart$", "Disallow: /catalogo/*",
        "Disallow: /index.php?action=*", "Allow: *utm_source=google_products&utm_medium*",
        "Disallow: /private", "Allow: /private/open",
        "User-agent: EtaoSpider", "Disallow: /",
    ]), http_client.HEADERS["User-Agent"])
    base = "https://www.tradeinn.com"
    assert robots.allowed(f"{base}/techinn/pt/consolas-jogos-playstation/19292/s")
    assert robots.allowed(f"{base}/techinn/pt/consolas-jogos-playstation/19292/s?page=2")
    assert not robots.allowed(f"{base}/techinn/pt/p?query=zelda")
    assert not robots.allowed(f"{base}/techinn/pt/ofertas/123")
    assert not robots.allowed(f"{base}/techinn/pt/cart") and robots.allowed(f"{base}/techinn/pt/cart/help")
    assert not robots.allowed("https://www.xtralife.com/catalogo/ps5")
    assert not robots.allowed(f"{base}/index.php?action=login")
    assert not robots.allowed(f"{base}/private/x") and robots.allowed(f"{base}/private/open/x")   # longest rule wins
    # another bot's group isn't ours; an empty Disallow allows everything
    assert RobotsRules.parse("User-agent: *\nDisallow:", "Mozilla/5.0").allowed(f"{base}/anything")


def test_a_group_naming_our_bot_is_ours():
    """Matched by the product token (RFC 9309), not by any word in the rest of the User-Agent."""
    from scrapers.base.robots import RobotsRules

    ours = "Project10794-bot/1.0 (+https://github.com/Barbaaz/Project-10794)"
    named = "User-agent: *\nDisallow:\n\nUser-agent: project10794-bot\nDisallow: /private"
    assert not RobotsRules.parse(named, ours).allowed("https://shop.test/private/x")
    assert RobotsRules.parse(named, ours).allowed("https://shop.test/games")
    others = "User-agent: *\nDisallow:\n\nUser-agent: github\nDisallow: /"      # "github" is in our link, not our name
    assert RobotsRules.parse(others, ours).allowed("https://shop.test/games")


@pytest.mark.parametrize("status", [403, 500, 503])
def test_robots_txt_refused_or_broken_means_crawl_nothing(clock, status):
    """401 / 403: the site refuses crawlers; 5xx: it can't say what's allowed, so nothing is (RFC 9309)."""
    c = client(FakeSession(robots=FakeResponse(status=status)))
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


def test_session_never_retries_a_block():
    """The real session's retries: 429 with Retry-After isn't waited out and asked again (CSTech, 10-07)."""
    retry = HttpClient().session.get_adapter("https://shop.test/").max_retries
    assert not retry.is_retry("GET", 429, has_retry_after=True)
    assert not retry.is_retry("GET", 403, has_retry_after=True)
    assert retry.is_retry("GET", 503, has_retry_after=True)
    assert retry.is_retry("GET", 502)


def test_post_follows_the_same_rules(clock):
    session = FakeSession(robots="User-agent: *\nDisallow: /private",
                          responses={"https://shop.test/ajax": FakeResponse(status=429)})
    c = client(session)
    with pytest.raises(RobotsDisallowed):
        c.post_json("https://shop.test/private", {"page": 1})
    with pytest.raises(StoreBlocked):
        c.post_json("https://shop.test/ajax", {"page": 1})
    assert session.methods == ["POST"]


def test_request_budget(clock):
    c = client(FakeSession(), max_requests=2)
    c.get_text("https://shop.test/a")
    c.get_text("https://shop.test/b")
    with pytest.raises(RequestBudgetExceeded):
        c.get_text("https://shop.test/c")
    assert c.request_count == 2


def pre_orders(n):
    return [{"url": f"https://x/{i}", "external_name": f"Game {i} PS5", "is_preorder": True,
             "release_date": None, "release_date_checked": False} for i in range(n)]


def test_product_page_lookups_stop_when_blocked():
    from scrapers.press_start.scraper import PressStartScraper

    calls = []

    def blocked(url):
        calls.append(url)
        raise StoreBlocked("403")

    scraper = PressStartScraper()
    scraper.fetch_product_page = blocked
    with pytest.raises(StoreBlocked):
        scraper.add_product_pages(pre_orders(10))
    assert len(calls) == 1


def test_product_page_lookups_are_capped_per_run():
    from scrapers.press_start.scraper import PressStartScraper

    scraper = PressStartScraper()
    scraper.max_product_pages = 3
    scraper.fetch_product_page = lambda url: {}
    products = pre_orders(10)
    scraper.add_product_pages(products)
    assert sum(p["release_date_checked"] for p in products) == 3
