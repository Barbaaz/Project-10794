"""
The knowledge base names real files (user, 2026-11-06): every link and every path in a code span in
AGENTS.md, GLOSSARY.md and docs/ points at something in the repo, so a file moved or deleted shows up
here instead of leaving a page that sends readers nowhere.

Checked: links to files, relative to the page ([Architecture](architecture.md)), and code spans that
start with one of the repo's folders (`app/routes/auth.py`, `tests/fixtures/`). Skipped: web links,
anchors, fenced code blocks, placeholders (`scrapers/<store>/`, `database/*.sql`, `00NN`, `…`) and
the folders the app makes while it runs, which aren't in git.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = [ROOT / "AGENTS.md", ROOT / "GLOSSARY.md", *sorted((ROOT / "docs").rglob("*.md"))]
RUNTIME_FOLDERS = {"instance", "logs", "backups"}
FOLDERS = {p.name for p in ROOT.iterdir()
           if p.is_dir() and not p.name.startswith((".", "_")) and p.name not in RUNTIME_FOLDERS}

FENCED = re.compile(r"^```.*?^```", re.S | re.M)
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
CODE = re.compile(r"`([^`\n]+)`")
PLACEHOLDER = re.compile(r"[<>*…{}]|NN")
WEB = re.compile(r"[a-z]+:")


def named_paths(page):
    """(the path as written, where it points) for each file or folder the page names."""
    text = FENCED.sub("", page.read_text(encoding="utf-8"))
    for target in LINK.findall(text):
        target = target.split("#")[0]
        if target and not WEB.match(target):
            yield target, page.parent / target
    for span in CODE.findall(text):
        span = re.sub(r":\d+$", "", span)              # file.py:42
        if "/" not in span or " " in span or PLACEHOLDER.search(span) or span.split("/")[0] not in FOLDERS:
            continue
        yield span, ROOT / span


@pytest.mark.parametrize("page", [p for p in PAGES if p.exists()], ids=lambda p: p.relative_to(ROOT).as_posix())
def test_paths_named_in_the_docs_exist(page):
    missing = [written for written, path in named_paths(page) if not path.exists()]
    assert missing == [], f"{page.relative_to(ROOT).as_posix()} names paths that don't exist: {missing}"


def test_a_missing_path_is_caught(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("See [gone](gone.md), `app/nowhere.py`, `scrapers/<store>/` and [web](https://example.com).",
                    encoding="utf-8")
    missing = [written for written, path in named_paths(page) if not path.exists()]
    assert missing == ["gone.md", "app/nowhere.py"]
