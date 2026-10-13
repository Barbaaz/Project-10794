"""
The gamer names and channels a user shows on their profile (user, 2026-10-13): PSN, Xbox, Steam,
Nintendo, Epic, YouTube, Twitch. Each optional; typed as a name or pasted as a link, kept in one form.
Links are only ever built here from what passed the checks, so a profile can't carry another address.
"""
import re

from app.services.auth_service import AccountError

# kind → (the check on what's kept, the link made from it or None: shown as text)
KINDS = {
    "psn": (re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,15}"), None),
    "xbox": (re.compile(r"[A-Za-z0-9][A-Za-z0-9 ]{0,14}(#\d{1,4})?"), None),
    "steam": (re.compile(r"(id/[A-Za-z0-9_-]{2,32}|profiles/\d{17})"), "https://steamcommunity.com/{}"),
    "nintendo": (re.compile(r"SW-\d{4}-\d{4}-\d{4}"), None),
    "epic": (re.compile(r"[^\s<>\"'`][^<>\"'`]{1,30}[^\s<>\"'`]"), None),
    "youtube": (re.compile(r"(@[A-Za-z0-9._-]{3,30}|channel/UC[A-Za-z0-9_-]{22})"), "https://www.youtube.com/{}"),
    "twitch": (re.compile(r"[A-Za-z0-9_]{4,25}"), "https://www.twitch.tv/{}"),
}

_URL = re.compile(r"^(https?://)?(www\.|m\.)?", re.I)


def _plain(kind, text):
    """What was typed or pasted, in the form that's kept (still to be checked)."""
    if kind == "steam":
        text = _URL.sub("", text)
        text = re.sub(r"^steamcommunity\.com/", "", text, flags=re.I).strip("/")
        return text if text.startswith(("id/", "profiles/")) else f"id/{text}"
    if kind == "nintendo":
        digits = re.sub(r"\D", "", text)
        return f"SW-{digits[:4]}-{digits[4:8]}-{digits[8:]}" if len(digits) == 12 else text
    if kind == "youtube":
        text = re.sub(r"^youtube\.com/", "", _URL.sub("", text), flags=re.I).strip("/").split("?")[0]
        return text if text.startswith(("@", "channel/")) else f"@{text}"
    if kind == "twitch":
        return re.sub(r"^twitch\.tv/", "", _URL.sub("", text), flags=re.I).strip("/").split("?")[0]
    return text


def cleaned(changes, current):
    """{kind: typed text} over the current {kind: kept}: the new {kind: kept}; empty text takes it off."""
    accounts = dict(current)
    for kind, text in changes.items():
        text = (text or "").strip()
        if not text:
            accounts.pop(kind, None)
            continue
        value = _plain(kind, text)
        if not KINDS[kind][0].fullmatch(value):
            raise AccountError(f"{kind}_invalid")
        accounts[kind] = value
    return {kind: accounts[kind] for kind in KINDS if kind in accounts}


def shown(accounts):
    """[{kind, name, url}] in a fixed order, for the profile: url None where there's no page to link."""
    result = []
    for kind, (_, link) in KINDS.items():
        value = (accounts or {}).get(kind)
        if not value:
            continue
        name = value.removeprefix("id/") if kind == "steam" else value
        if kind == "steam" and value.startswith("profiles/") or kind == "youtube" and value.startswith("channel/"):
            name = None           # a number: the page shows the service's name instead
        result.append({"kind": kind, "name": name, "url": link.format(value) if link else None})
    return result
