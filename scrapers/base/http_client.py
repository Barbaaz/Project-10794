import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}


class HttpClient:
    """requests.Session with a timeout and automatic retries on temporary errors."""

    def __init__(self, timeout=30, retries=3, backoff=1.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        retry = Retry(
            total=retries,
            backoff_factor=backoff,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def get(self, url, params=None):
        response = self.session.get(url, params=params, timeout=self.timeout)
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
