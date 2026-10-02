"""
Matching shortened store names to a game we already know, for stores that abbreviate
(Rádio Popular: "TALES OF ETERNIA REMAS", "FF VII REVELATION", "STAR WAR GALACTIC RACER").

Only used when the exact name key finds nothing. Joining two different games is worse than a
duplicate (one game's prices on another's page), so the rules are strict:
- the numbers must be the same ("lets sing 2027" never matches "lets sing 2023");
- the first word must be the same, the last word the same or its start ("remas" → "remastered"),
  so "god of war" doesn't match "god of war ragnarok";
- only small linking words may be missing ("doom dark ages" → "doom the dark ages"): a missing
  real word often is the difference ("f1 23" / "f1 manager 23", "resident evil 2" / "resident
  evil revelations 2", "lets sing 2027" / "lets sing abba 2027"); other words may be a cut-off
  start ("war" → "wars", "remas" → "remastered");
- exactly one known game may qualify on that platform.
"""

SKIPPABLE = {"the", "of", "and", "a", "an", "e", "o", "de", "do", "da"}

ABBREVIATIONS = {
    "ff": "final fantasy",
    "gta": "grand theft auto",
    "cod": "call of duty",
}

ROMAN = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv", "xvi"}
MIN_PREFIX = 3   # a cut-off word keeps at least 3 letters


def expand(key):
    return " ".join(ABBREVIATIONS.get(w, w) for w in key.split())


def numbers(words):
    return sorted(w for w in words if w.isdigit() or w in ROMAN)


def same_word(short, full, allow_prefix):
    if short == full:
        return True
    return allow_prefix and len(short) >= MIN_PREFIX and not short.isdigit() and full.startswith(short)


def fits(short_key, full_key):
    """True when short_key could be a shortened way of writing full_key."""
    short, full = expand(short_key).split(), expand(full_key).split()
    if len(short) < 2 or len(short) > len(full) or numbers(short) != numbers(full):
        return False
    if short[0] != full[0] or not same_word(short[-1], full[-1], allow_prefix=True):
        return False

    # the words in between, in order: each the same word or its start; the full name may
    # have extra linking words ("the", "of"...) but no other extra word
    j = 1
    for word in short[1:-1]:
        while j < len(full) - 1 and not same_word(word, full[j], allow_prefix=True):
            if full[j] not in SKIPPABLE:
                return False
            j += 1
        if j >= len(full) - 1:
            return False
        j += 1
    return all(w in SKIPPABLE for w in full[j:-1])


def close_match(key, known_keys):
    """The one known key that `key` is a shortened form of, or None (no candidate, or several)."""
    if key in known_keys:
        return key
    found = [k for k in known_keys if fits(key, k)]
    return found[0] if len(found) == 1 else None


class KeyIndex:
    """
    Known game keys of one platform, to send a name to its fuller known form:
    resolve("doom dark ages") → "doom the dark ages" when that game is known.
    Indexed by first word (fits() needs the same first word), so it stays fast.
    """

    def __init__(self, keys=()):
        self.by_first = {}
        for key in keys:
            self.add(key)

    def add(self, key):
        words = expand(key).split()
        if words:
            self.by_first.setdefault(words[0], set()).add(key)

    def __contains__(self, key):
        words = expand(key).split()
        return bool(words) and key in self.by_first.get(words[0], ())

    def resolve(self, key):
        """
        The fuller known key `key` is a short form of, else `key` itself. Two keys that fit each
        other ("gta trilogy" / "grand theft auto trilogy") both go to the longer one.
        """
        words = expand(key).split()
        if not words:
            return key
        found = [k for k in self.by_first.get(words[0], ()) if k != key and fits(key, k)]
        if len(found) != 1:
            return key
        other = found[0]
        if fits(other, key) and (len(other), other) < (len(key), key):
            return key
        return other
