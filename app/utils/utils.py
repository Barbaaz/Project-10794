import re

# Codes match the platforms table. Order matters: the first match wins.
# - "Switch 2" before "Switch"
# - Series X|S before One: a cross-gen disc ("Xbox One / Series X") counts as Series X|S,
#   so it matches the same disc sold as just "Xbox Series X" by another store
PLATFORM_PATTERNS = [
    ("Switch2", r"\b(nintendo\s+)?switch\s*2\b|\bns2\b"),
    ("Switch", r"\b(nintendo\s+)?switch\b"),
    ("PS5", r"\bps5\b|\bplaystation\s*5\b"),
    ("PS4", r"\bps4\b|\bplaystation\s*4\b"),
    ("PS3", r"\bps3\b|\bplaystation\s*3\b"),
    ("XboxSeries", r"\bxbox\s+series\b|\bseries\s+[xs]\b|\bx\s*\|\s*s\b|\bxsx\b"),
    ("XboxOne", r"\bxbox\s+one\b"),
    ("Xbox", r"\bxbox\b"),     # generic, resolved by detetar_plataforma()
    ("PC", r"\bpc\b"),
]

XBOX_PLATFORMS = {"XboxSeries", "XboxOne"}


def extrair_consola(*textos):
    """Platform code from a product name (or other texts, tried in order), or None."""
    for texto in textos:
        if not texto:
            continue

        for code, pattern in PLATFORM_PATTERNS:
            if re.search(pattern, texto, re.IGNORECASE):
                return code

    return None


def detetar_plataforma(nome, categoria=None, *extra):
    """
    Platform of a product. The store category wins ("PS4 | PS5" in the PS4 category is PS4),
    except between the two Xboxes, where the name is more precise than some categories.
    A name that only says "Xbox" counts as Series X|S.
    """
    titulo = extrair_consola(nome, *extra)

    if categoria in XBOX_PLATFORMS and titulo in XBOX_PLATFORMS:
        return titulo
    if categoria:
        return categoria
    return "XboxSeries" if titulo == "Xbox" else titulo
