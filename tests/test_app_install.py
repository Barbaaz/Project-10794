"""The site as an app on a phone: the manifest, the service worker (static/sw.js) and what it may save."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SW = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")


@pytest.fixture
def client():
    from app.web import app
    return app.test_client()


def test_the_service_worker_is_served_from_the_root_and_always_checked(client):
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert response.mimetype == "text/javascript"
    assert response.headers["Cache-Control"] == "no-cache"


def test_the_manifest_and_its_icons(client):
    response = client.get("/manifest.webmanifest")
    assert response.mimetype == "application/manifest+json"
    manifest = json.loads(response.data)
    assert manifest["display"] == "standalone" and manifest["start_url"] == "/"
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes                     # what Android needs to offer installing
    assert any(icon.get("purpose") == "maskable" for icon in manifest["icons"])
    for icon in manifest["icons"]:
        assert (ROOT / icon["src"].lstrip("/")).exists(), icon["src"]


def test_files_saved_on_install_exist():
    precache = re.search(r"const PRECACHE = \[(.*?)\];", SW, re.DOTALL).group(1)
    for path in re.findall(r'"(/static/[^"]+)"', precache):
        assert (ROOT / path.lstrip("/")).exists(), path


def test_every_page_links_the_manifest():
    for page in (ROOT / "templates").glob("*.html"):
        html = page.read_text(encoding="utf-8")
        assert '<link rel="manifest" href="/manifest.webmanifest">' in html, page.name
        assert "apple-touch-icon" in html, page.name


def public_api():
    """The service worker's PUBLIC_API patterns (JavaScript regexes that Python reads the same way)."""
    block = re.search(r"const PUBLIC_API = \[(.*?)\];", SW, re.DOTALL).group(1)
    return [re.compile(p.replace(r"\/", "/")) for p in re.findall(r"/(\^.*?\$)/", block)]


@pytest.mark.parametrize("path", [
    "/api/games", "/api/games/catalog", "/api/games/editions", "/api/games/12", "/api/games/12/prices",
    "/api/discounts", "/api/discounts/featured", "/api/deals", "/api/preorders", "/api/releases",
    "/api/stores", "/api/platforms", "/api/genres", "/api/tags", "/api/listings",
])
def test_public_reads_are_saved_for_offline_use(path):
    assert any(p.match(path) for p in public_api())


@pytest.mark.parametrize("path", [
    # personal: never saved on the device (another person may use it after logging out)
    "/api/auth/me", "/api/collection", "/api/collection/deals", "/api/conversations", "/api/conversations/unread",
    "/api/listings/mine", "/api/ratings/pending", "/api/mod/reports", "/api/users/ana/collection",
    # the same for everyone except the writer / seller ("mine", owner buttons)
    "/api/games/12/reviews", "/api/listings/7", "/api/users/ana",
])
def test_personal_answers_are_never_saved(path):
    assert not any(p.match(path) for p in public_api())
