"""The header on every page (templates/_header.html, filled by static/common.js) has ids of its own: a page
reusing one gets the header's element from getElementById (2026-10-13: the profile's "Ver a coleção" had
the header's collection-link id, so it never got its address and the header's icon took it)."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HEADER = (ROOT / "templates" / "_header.html").read_text(encoding="utf-8") + (ROOT / "static" / "common.js").read_text(encoding="utf-8")
HEADER_IDS = set(re.findall(r'\bid="([A-Za-z][\w-]*)"', HEADER))
PAGES = [p for p in (ROOT / "templates").glob("*.html") if not p.name.startswith("_")]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_dont_reuse_the_headers_ids(page):
    ids = set(re.findall(r'\bid="([A-Za-z][\w-]*)"', page.read_text(encoding="utf-8")))
    script = ROOT / "static" / "pages" / f"{page.stem}.js"
    if script.exists():
        ids |= set(re.findall(r'\bid="([A-Za-z][\w-]*)"', script.read_text(encoding="utf-8")))
    assert ids & HEADER_IDS == set()
