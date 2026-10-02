"""The page texts (static/i18n.js): every key once in each language."""
import re
from collections import Counter
from pathlib import Path

TEXT = (Path(__file__).resolve().parent.parent / "static" / "i18n.js").read_text(encoding="utf-8")


def test_each_key_once_per_language():
    pt, en = TEXT.split("\n    en: {")
    keys = lambda part: Counter(re.findall(r"^        ([a-z_0-9]+):", part, flags=re.MULTILINE))
    pt_keys, en_keys = keys(pt), keys(en)
    # a key written twice in one language silently replaces the first text
    assert [k for k, n in pt_keys.items() if n > 1] == []
    assert [k for k, n in en_keys.items() if n > 1] == []
    assert set(pt_keys) == set(en_keys)
