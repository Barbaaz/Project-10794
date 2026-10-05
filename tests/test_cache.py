"""The small answer cache (app/services/common.py): keyed by request values (a platform typed in the
address), so it must not grow without end."""
import pytest

from app.services import common


@pytest.fixture(autouse=True)
def empty_cache():
    common.clear_cache()
    yield
    common.clear_cache()


def test_cached_answers_are_reused():
    calls = []
    compute = lambda: calls.append(1) or "answer"
    assert common.cached("key", compute) == common.cached("key", compute) == "answer"
    assert len(calls) == 1


def test_the_cache_keeps_at_most_max_entries(monkeypatch):
    monkeypatch.setattr(common, "MAX_CACHED", 3)
    for i in range(10):
        assert common.cached(("featured", f"platform-{i}"), lambda: i) == i
    assert len(common._cache) <= 3
    assert ("featured", "platform-9") in common._cache                   # the newest kept
