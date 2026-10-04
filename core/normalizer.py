import re
import unicodedata

# Removed from names so the same game matches across stores.
# Platform and condition are stored in their own columns, so they don't belong in the name.
NOISE_PATTERNS = [
    r"semi[\s-]?novo", r"seminovo", r"usad[oa]", r"novo",
    r"(nintendo\s+)?switch\s*2(\s+edition)?", r"(nintendo\s+)?switch",
    r"playstation\s*[345]?", r"ps[345]",
    # "Xbox One / Series X", "XBOX ONE | X|S", "Xbox One & Series X", "Xbox Series X|S", "X/S", "Xbox"
    r"xbox\s+one\s*[/|&]\s*(xbox\s+)?(series\s+)?x(\s*[|/]\s*s)?",
    r"xbox\s+series(\s+[xs](\s*[|/]\s*s)?)?", r"xbox\s+one", r"xbox", r"series\s+x(\s*[|/]\s*s)?",
    r"pc",
]
NOISE_REGEX = re.compile(r"\b(" + "|".join(NOISE_PATTERNS) + r")\b", re.IGNORECASE)

# Roman numerals are numbers in keys ("Dark Souls III" = "DARK SOULS 3", "GTA V" = "GTA 5").
# "i" and "x" stay letters: "Octopath Traveler I", "Mega Man X", "I Am Bread"
NUMERALS = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9",
            "xi": "11", "xii": "12", "xiii": "13", "xiv": "14", "xv": "15", "xvi": "16"}


def numerals(key):
    """A normalized key with its Roman numerals as numbers (also used on keys stored before this rule)."""
    return " ".join(NUMERALS.get(w, w) for w in key.split())


PLUS_BETWEEN_NUMBERS = re.compile(r"(?<=\d)\s*\+\s*(?=\d)")


def split_plus_numbers(key, title):
    """
    A key stored before "+" between numbers became a space: "pro skater 34" → "pro skater 3 4"
    when its title says "3+4" (the key alone can't tell "3+4" from 34).
    """
    for a, b in re.findall(r"(\d+)\s*\+\s*(\d+)", title or ""):
        key = re.sub(rf"\b{a}{b}\b", f"{a} {b}", key)
    return key


def clean_name(name):
    """
    Removes brackets, platform and condition but keeps case and punctuation, for display:
    "Silent Hill: Townfall [USADO] PS5" → "Silent Hill: Townfall"
    """
    # remover conteúdo entre parênteses / parênteses retos: "(PT)", "[USADO]"
    name = re.sub(r"[\(\[].*?[\)\]]", " ", name)

    # remover ruído comum (só palavras inteiras)
    name = NOISE_REGEX.sub(" ", name)

    # Press Start sometimes writes "Jogo Street Fighter 6"
    name = re.sub(r"^\s*jogo\s+", "", name, flags=re.IGNORECASE)

    name = " ".join(name.split())
    return name.strip(" -–:|/,&")


def normalize_name(name):
    """Key for matching: "Marvel's Spider-Man 2 (PT) PS5" → "marvels spiderman 2" """
    name = clean_name(name).lower()

    # remover acentos: "Pokémon" → "pokemon"
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))

    # "+" between numbers is a space: "Pro Skater 3+4" = "Pro Skater 3 + 4" → "3 4", not "34"
    name = PLUS_BETWEEN_NUMBERS.sub(" ", name)

    # remover símbolos: "Spider-Man" → "spiderman", "Assassin's" → "assassins"
    name = re.sub(r"[^a-z0-9\s]", "", name)

    # letras e números separados, para "Vol.2", "Vol. 2" e "vol2" darem o mesmo: "vol 2"
    name = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", name)

    # normalizar espaços; numerais romanos como números
    return numerals(name)
