"""The secret key signs the login cookie: with a known or short one, anyone could forge a login as any user."""
import pytest

from app import config


@pytest.mark.parametrize("key", ["change-me-to-a-long-random-text", "short", "x" * 31])
def test_a_placeholder_or_short_secret_key_is_refused(monkeypatch, key):
    monkeypatch.setenv("SECRET_KEY", key)
    with pytest.raises(SystemExit, match="SECRET_KEY"):
        config._secret_key()


def test_a_long_random_secret_key_is_used(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "3f" * 32)
    assert config._secret_key() == "3f" * 32
