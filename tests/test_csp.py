"""The Content-Security-Policy only runs scripts from files (ours and the hashed CDN ones): an injected
<script> or onclick="…" in a page is refused by the browser. So the pages themselves have none."""
import re
from pathlib import Path

import pytest

import app.web as web

ROOT = Path(__file__).resolve().parent.parent
PAGES = [*(ROOT / "templates").glob("*.html"), ROOT / "static" / "offline.html"]
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>")
INLINE_HANDLER = re.compile(r"""\son[a-z]+\s*=\s*["'`]""")


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_have_no_inline_scripts_or_handlers(page):
    html = page.read_text(encoding="utf-8")
    assert INLINE_SCRIPT.findall(html) == []
    assert INLINE_HANDLER.findall(html) == []


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_page_scripts_exist(page):
    for src in re.findall(r'<script src="(/static/[^"]+)"', page.read_text(encoding="utf-8")):
        assert (ROOT / src.lstrip("/")).exists(), src


@pytest.mark.parametrize("js", sorted((ROOT / "static").rglob("*.js")), ids=lambda p: p.name)
def test_scripts_add_no_inline_handlers(js):
    """HTML built by scripts: listeners, never onclick="…" (the policy would refuse it)."""
    code = re.sub(r"^\s*//.*$", "", js.read_text(encoding="utf-8"), flags=re.MULTILINE)
    assert INLINE_HANDLER.findall(code) == []


def test_the_policy_only_runs_scripts_from_files():
    policy = web.app.test_client().get("/").headers["Content-Security-Policy"]
    assert "script-src 'self' https://cdn.jsdelivr.net/npm/" in policy
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy


def test_the_offline_page_works_offline():
    """Shown by the service worker without a connection: its script must be saved at install."""
    sw = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
    assert '"/static/pages/offline.js"' in sw
