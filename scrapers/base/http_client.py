"""
HTTP for the scrapers, built to stay polite so the stores don't block us:

- One request at a time, at least MIN_INTERVAL seconds (+ random jitter) between requests
  to the same site, retries included. A larger Crawl-delay in robots.txt wins.
- URLs disallowed by the site's robots.txt are never fetched.
- 403 / 429 (after Retry-After) stop the run: StoreBlocked. We don't keep knocking.
- At most `max_requests` per run: RequestBudgetExceeded.
"""
import logging
import random
import time
import urllib.robotparser
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

MIN_INTERVAL = 3.0      # seconds between requests to the same site
JITTER = 2.0            # + random 0..JITTER seconds, so requests don't come at a fixed rhythm
MAX_REQUESTS = 600      # per store per run (a full Press Start run needs ~150)


class StoreBlocked(Exception):
    """The store answered 403 / 429: stop scraping it for now."""


class RequestBudgetExceeded(Exception):
    """More requests than allowed in one run; something is looping."""


class RobotsDisallowed(Exception):
    """The site's robots.txt asks crawlers not to fetch this URL."""


class HttpClient:
    def __init__(self, timeout=30, retries=3, min_interval=MIN_INTERVAL, jitter=JITTER, max_requests=MAX_REQUESTS):
        self.timeout = timeout
        self.min_interval = min_interval
        self.jitter = jitter
        self.max_requests = max_requests
        self.request_count = 0
        self._last_request = {}     # host → time of the last request
        self._robots = {}           # host → RobotFileParser (or None if robots.txt couldn't be read)

        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        # Retries only for temporary server errors, with growing waits (2, 4, 8 s).
        # 403 / 429 are not retried here: they mean "slow down / go away".
        retry = Retry(
            total=retries,
            backoff_factor=2,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def get(self, url, params=None):
        host = urlsplit(url).netloc
        if not self._allowed(url, host):
            raise RobotsDisallowed(url)

        if self.request_count >= self.max_requests:
            raise RequestBudgetExceeded(f"{self.request_count} requests to {host} in this run")

        self._wait(host)
        self.request_count += 1
        response = self.session.get(url, params=params, timeout=self.timeout)
        self._last_request[host] = time.monotonic()

        if response.status_code in (403, 429):
            wait = response.headers.get("Retry-After")
            raise StoreBlocked(f"{host} answered {response.status_code}"
                               + (f" (Retry-After: {wait})" if wait else "") + f" for {url}")

        response.raise_for_status()
        return response

    def get_text(self, url, params=None):
        response = self.get(url, params)

        # Without a charset header requests assumes ISO-8859-1, which breaks accents
        if "charset" not in response.headers.get("content-type", "").lower():
            response.encoding = response.apparent_encoding

        return response.text

    def get_json(self, url, params=None):
        return self.get(url, params).json()

    # --- politeness ------------------------------------------------------

    def _wait(self, host):
        last = self._last_request.get(host)
        if last is None:
            return
        interval = max(self.min_interval, self._crawl_delay(host)) + random.uniform(0, self.jitter)
        remaining = interval - (time.monotonic() - last)
        if remaining > 0:
            time.sleep(remaining)

    def _robots_for(self, host):
        if host not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            try:
                response = self.session.get(f"https://{host}/robots.txt", timeout=self.timeout)
                self._last_request[host] = time.monotonic()
                if response.status_code in (401, 403):
                    parser.disallow_all = True      # the site refuses even robots.txt: crawl nothing
                else:
                    # No robots.txt (404) means everything is allowed
                    parser.parse(response.text.splitlines() if response.ok else [])
                self._robots[host] = parser
            except requests.RequestException as e:
                log.warning("robots.txt of %s unreadable (%s); continuing with the default delay", host, e)
                self._robots[host] = None
        return self._robots[host]

    def _allowed(self, url, host):
        robots = self._robots_for(host)
        return robots is None or robots.can_fetch(HEADERS["User-Agent"], url)

    def _crawl_delay(self, host):
        robots = self._robots_for(host)
        delay = robots.crawl_delay(HEADERS["User-Agent"]) if robots else None
        return float(delay or 0)
