"""esc() in static/common.js: text from users (display names, notes, titles) goes into page HTML through it,
also inside attributes (title="…", value="…"), so quotes must be escaped too. Run with Node when it's installed."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

COMMON_JS = (Path(__file__).resolve().parent.parent / "static" / "common.js").read_text(encoding="utf-8")

node = shutil.which("node")
pytestmark = pytest.mark.skipif(node is None, reason="Node isn't installed")


def esc(text):
    """esc(text) as the page computes it: the function's code from common.js, run by Node."""
    code = re.search(r"^const ESCAPES = .*?^function esc\(text\) \{.*?^\}", COMMON_JS, re.MULTILINE | re.DOTALL)
    assert code, "esc() not found in static/common.js"
    script = f"{code.group(0)}\nprocess.stdout.write(JSON.stringify(esc({json.dumps(text)})));"
    return json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)


def test_tags_and_ampersands_are_escaped():
    assert esc("<script>alert(1)</script> & co") == "&lt;script&gt;alert(1)&lt;/script&gt; &amp; co"


def test_quotes_are_escaped_so_text_cant_leave_an_attribute():
    # a display name like this in title="…" (the market tab's seller buttons) added an event handler
    assert esc('x" onmouseover="alert(1)') == "x&quot; onmouseover=&quot;alert(1)"
    assert esc("x' onfocus='alert(1)") == "x&#39; onfocus=&#39;alert(1)"


def test_empty_values():
    assert esc(None) == ""
    assert esc("") == ""
