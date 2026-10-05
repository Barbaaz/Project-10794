"""Security headers on every answer (app/web.py): no framing by other sites (clickjacking), no guessing of
content types, no full addresses (a password-reset link's token) sent to other sites, HTTPS remembered."""
import pytest

import app.web as web


@pytest.fixture
def client():
    return web.app.test_client()


def test_every_answer_has_the_security_headers(client):
    for path in ("/", "/static/common.js", "/sw.js"):
        headers = client.get(path).headers
        assert headers["X-Content-Type-Options"] == "nosniff", path
        assert headers["X-Frame-Options"] == "DENY", path
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"], path
        assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin", path


def test_https_is_only_remembered_when_served_over_https(client, monkeypatch):
    assert "Strict-Transport-Security" not in client.get("/").headers      # plain HTTP on a dev machine
    monkeypatch.setattr(web, "COOKIE_SECURE", True)
    assert client.get("/").headers["Strict-Transport-Security"].startswith("max-age=")
