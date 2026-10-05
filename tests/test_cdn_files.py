"""Files from the CDN (Bootstrap, Chart.js) carry their hash (Subresource Integrity): if the CDN served
anything else, the browser refuses it instead of running it on our pages."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = [*(ROOT / "templates").glob("*.html"), ROOT / "static" / "offline.html"]
CDN_TAG = re.compile(r"<(?:script|link)\b[^>]*https://cdn\.jsdelivr\.net[^>]*>")


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_cdn_files_carry_their_hash(page):
    tags = CDN_TAG.findall(page.read_text(encoding="utf-8"))
    assert tags, "no CDN file found: the pattern needs updating"
    for tag in tags:
        assert re.search(r'integrity="sha384-[A-Za-z0-9+/=]{64}"', tag), tag
        assert 'crossorigin="anonymous"' in tag, tag            # integrity needs a CORS request


def test_the_service_worker_never_keeps_opaque_answers():
    """An opaque (no-CORS) copy can't be checked against a hash: the page would lose its styles."""
    sw = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
    assert '"opaque"' not in sw
