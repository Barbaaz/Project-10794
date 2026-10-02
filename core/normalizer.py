import re
import unicodedata

# Removed from names so the same game matches across stores.
# Platform and condition are stored in their own columns, so they don't belong in the name.
NOISE_PATTERNS = [
    r"semi[\s-]?novo", r"seminovo", r"usad[oa]", r"novo",
    r"(nintendo\s+)?switch\s*2(\s+edition)?", r"(nintendo\s+)?switch",
    r"playstation\s*[345]?", r"ps[345]",
    # "Xbox One / Series X", "XBOX ONE | X|S", "Xbox One & Series X", "Xbox Series X|S", "Xbox"
    r"xbox\s+one\s*[/|&]\s*(xbox\s+)?(series\s+)?x(\s*\|\s*s)?",
    r"xbox\s+series(\s+[xs](\s*\|\s*s)?)?", r"xbox\s+one", r"xbox", r"series\s+x(\s*\|\s*s)?",
    r"pc",
]
NOISE_REGEX = re.compile(r"\b(" + "|".join(NOISE_PATTERNS) + r")\b", re.IGNORECASE)


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

    # remover símbolos: "Spider-Man" → "spiderman", "Assassin's" → "assassins"
    name = re.sub(r"[^a-z0-9\s]", "", name)

    # normalizar espaços
    return " ".join(name.split())
