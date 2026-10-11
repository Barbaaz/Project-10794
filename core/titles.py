"""
Which of the stores' spellings of a game (or edition) to show (pipeline/rematch.py, pipeline/matcher.py).
The most common one used to win, ties alphabetically, so a rematch would have renamed ~75 games,
many for the worse ("FIFA 23" → "FIFA® 23", "Oddworld: Soulstorm" → "Oddworld Soulstorm", "Lords of
the Fallen" ↔ "Lords of The Fallen"). Now a name only changes for one that is better written:
1. fewer faults (flaws()): shouting in capitals, ® / ™, "Vii" for VII, "Of The" / "A" capitalised
   inside the title (each one), "Gabby'S", "1St";
2. as few faults, and clearly closer to IGDB's English name (CLOSER): "Watch Dogs: Legion".
Otherwise the current name stays, and never for the same name without its accents ("Ghost of
Yōtei", "Pokémon"). (Tried and dropped: more punctuation as a reason, which brought
"Persona 3 - Reload" and "Call of Duty : WWII".) Among equally good candidates: the closest to
IGDB's name, then the most common.
"""
import re
import unicodedata
from difflib import SequenceMatcher

# capitalised short words that belong in lower case inside a title ("Way Of The Hunter 2")
SMALL_WORDS = {"of", "the", "at", "in", "and", "on", "for", "to", "a", "an", "or", "vs"}
TRADEMARKS = re.compile(r"[®™©]")
ROMAN = re.compile(r"^[IVX]+$")
BAD_ROMAN = re.compile(r"\b(?:Ii|Iii|Iv|Vi|Vii|Viii|Ix|Xi|Xii|Xiii|Xiv|Xv|Xvi)\b")
CAPITAL_AFTER_APOSTROPHE = re.compile(r"[a-z]['’]S\b")
BAD_ORDINAL = re.compile(r"\b\d+(?:St|Nd|Rd|Th)\b")
MAX_SMALL_WORDS = 2       # capitalised "Of" / "The" counted up to this many times
CLOSER = 0.05            # how much closer to IGDB's name a candidate must be (difflib ratio)
SHOUT_LENGTH = 5          # one word in capitals this long is shouting ("UNKNOWN", "CRYSIS"; not "FIFA", "LEGO")


def flaws(title):
    """How many ways the title is badly written (0: none of those below)."""
    words = re.findall(r"[^\s:\-–+&/!]+", title)
    letters = [w for w in words if re.search(r"[A-Za-z]", w)]
    shouting = [w for w in letters if w.isupper() and not ROMAN.match(w) and len(re.sub(r"[^A-Za-z]", "", w)) >= 2]
    count = 0
    if letters and len(shouting) == len(letters) and len(letters) > 1:
        count += 3                                   # all in capitals
    elif _capital_run(letters):
        count += 2                                   # words shouted ("FINAL FANTASY VII Remake"): as bad as "In The"
    elif any(len(re.sub(r"[^A-Za-z]", "", w)) >= SHOUT_LENGTH for w in shouting):
        count += 1                                   # one word shouted ("CRYSIS Remastered")
    if TRADEMARKS.search(title):
        count += 1
    if BAD_ROMAN.search(title):
        count += 2                                   # "Vii": a wrong name, not just a style
    if CAPITAL_AFTER_APOSTROPHE.search(title) or BAD_ORDINAL.search(title):
        count += 1
    # "Of" / "The" with a capital, inside the title (not first, not after ":" or "-"), each one
    small = 0
    for previous, word in zip(re.split(r"\s+", title), re.split(r"\s+", title)[1:]):
        shouted = word.isupper() and len(word) > 1            # "THE" is shouting, counted above; "A" is not
        if word.lower() in SMALL_WORDS and word[:1].isupper() and not shouted and not previous.endswith((":", "-", "–")):
            small += 1
    return count + min(small, MAX_SMALL_WORDS)


def _capital_run(words):
    """Two words in capitals one after the other ("SLAY THE PRINCESS"), roman numerals aside."""
    caps = [w.isupper() and not ROMAN.match(w) and len(w) >= 2 for w in words]
    return any(a and b for a, b in zip(caps, caps[1:]))


def best_title(current, names, english=None):
    """
    The name to show: current, unless one of `names` ({name: how many products use it}) is better
    written (the rules above); among equally good candidates the closest to IGDB's name, then the
    most common.
    """
    if not names:
        return current
    like_english = lambda n: SequenceMatcher(None, n, english).ratio() if english else 0
    best = max(names, key=lambda n: (-flaws(n), like_english(n), names[n], n == current))
    if not current:
        return best
    if _plain(best) == _plain(current) and _plain(current) != current:
        return current                     # only its accents would go
    if flaws(best) < flaws(current):
        return best
    if flaws(best) == flaws(current) and english and like_english(best) >= like_english(current) + CLOSER:
        return best
    return current


def _plain(text):
    """The text without accents ("Yōtei" → "Yotei")."""
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
