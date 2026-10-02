"""
Splits a store's product name into the game and its edition:

    "NBA 2K26 - Kobe Bryant Edition PS5"            → "NBA 2K26"              + "Kobe Bryant Edition"
    "SILENT HILL TOWNFALL DAY ONE EDITION PS5"      → "SILENT HILL TOWNFALL"  + "Day One Edition"
    "EA Sports FC 26 Game Key Card Switch 2"        → "EA Sports FC 26"       + "Standard · Game Key Card"

("Código na caixa" / "Code in box" products are skipped entirely, see is_excluded().)

Stores write editions differently, so three rules are tried in order:
  1. "Title - Something Edition": everything after the last " - " is the edition.
     These phrases are remembered ("known phrases") to help rule 2.
  2. The name ends with a known phrase learned from rule 1 (e.g. "kobe bryant edition").
  3. The name ends with edition words (deluxe, day one, goty...), plus one unknown
     word when it ends in just "edition" ("Midnight Edition", "Explorer Edition").
     Weak words ("the", "game", "royal"...) only count before "edition" or a strong word.
"""
import re
import string
from dataclasses import dataclass

from core.normalizer import clean_name, normalize_name

EDITION_END = {"edition", "edicao", "version", "versao"}

# Can end a name on their own: "Hogwarts Legacy Deluxe"
STRONG_EDITION_WORDS = {
    "deluxe", "premium", "ultimate", "goty", "complete", "definitive", "collectors", "limited", "steelbook",
}

# Only part of an edition when followed by one of the above: "Day One Edition", "Game of the Year Edition".
# (Alone they are often part of the title: "Halloween: The Game", "Persona 5 Royal".)
EDITION_WORDS = EDITION_END | STRONG_EDITION_WORDS | {
    "standard", "gold", "collector", "special", "launch", "anniversary", "signature", "legendary",
    "digital", "platinum", "day", "one", "game", "of", "the", "year", "enhanced", "super", "royal", "master",
}

STANDARD_PHRASES = {"", "edition", "standard", "standard edition", "edicao standard"}

# Products we don't track at all: a download code (in a box or digital), no disc / cartridge
EXCLUDED = re.compile(
    r"c[oó]digo\s+(na\s+caixa|de\s+descarga|de\s+download|digital)|code\s+in\s+(a\s+)?box|[\[\(]\s*cod\s*[\]\)]"
    r"|[\[\(]\s*coib\s*[\]\)]"                      # Gaming Replay: "(COIB)" = code in box
    r"|download\s+digital|digital\s+download",
    re.IGNORECASE,
)

# Tags in brackets that make it a different product. Other brackets ("OFERTA DLC", "PT") are ignored.
BRACKET_TAGS = [
    ("PlayStation Hits", re.compile(r"playstation\s+hits", re.IGNORECASE)),
    ("Import JP", re.compile(r"import\s+jap|edi[cç][aã]o\s+japonesa", re.IGNORECASE)),
    ("Import US", re.compile(r"edi[cç][aã]o\s+americana", re.IGNORECASE)),       # Gaming Replay's imports
    ("Import Asia", re.compile(r"edi[cç][aã]o\s+asi[aá]tica", re.IGNORECASE)),
]
# A bonus that comes with the game, written after it: "Mortal Kombat 1 Switch - Oferta DLC" (Gaming Replay)
OFFER_SUFFIX = re.compile(r"\s+[-–]\s+oferta\b.*$", re.IGNORECASE)
# Tags that appear anywhere in the name
NAME_TAGS = [
    ("Game Key Card", re.compile(r"\bgame[\s-]*key[\s-]*card\b", re.IGNORECASE)),
]

DASH_SPLIT = re.compile(r"\s+[-–]\s+")
BRACKETS = re.compile(r"[\(\[]([^\)\]]*)[\)\]]")


@dataclass
class ParsedTitle:
    game_key: str        # normalized base title, matches games.normalized_title
    game_title: str      # base title for display
    edition_key: str     # matches game_editions.edition_key: "deluxe", "|Game Key Card" ("" = standard)
    edition_name: str    # for display
    phrase: str          # normalized edition phrase without tags


def is_excluded(name):
    """True for "Código na caixa" / "Code in box" / "Download Digital" products, which are not stored."""
    return bool(EXCLUDED.search(name))


def parse_title(name, known_phrases=()):
    text, tags = extract_tags(name)
    cleaned = clean_name(text)

    game_title, phrase, edition_text = split_on_dash(cleaned)
    if game_title is None:
        game_title, phrase, edition_text = split_on_words(cleaned, known_phrases)

    game_key = normalize_name(game_title)
    if not game_key:  # the whole name was edition words
        game_title, game_key, phrase, edition_text = cleaned, normalize_name(cleaned), "", ""

    if phrase in STANDARD_PHRASES:
        phrase, edition_text = "", ""

    edition_key = "|".join([edition_key_of(phrase)] + sorted(tags))
    edition_name = " · ".join([display_case(edition_text) or "Standard"] + sorted(tags))

    # The game title keeps its case ("NBA 2K26"); the matcher prefers a mixed-case name from another store
    return ParsedTitle(game_key, game_title.strip(" -–:|/,+"), edition_key, edition_name, phrase)


# Different ways of writing the same edition
EDITION_SYNONYMS = [
    ("game of the year", "goty"),
    ("day 1", "day one"),
    ("director s", "directors"),
    ("collector", "collectors"),
    ("edicao", ""), ("versao", ""),   # "Edição Deluxe"
]
# Words that don't change which edition it is
EDITION_FILLER = EDITION_END | {"the", "physical", "fisica", "ed"}


def edition_key_of(phrase):
    """
    One key per edition however a store writes it: "Deluxe Edition" = "Deluxe",
    "Steelbook Day One Edition" = "Day 1 Edition Steelbook", "Game of the Year" = "GOTY".
    The words are sorted, so their order doesn't matter.
    """
    text = f" {phrase} "
    for written, same in EDITION_SYNONYMS:
        text = text.replace(f" {written} ", f" {same} ")
    return " ".join(sorted({w for w in text.split() if w not in EDITION_FILLER}))


def extract_tags(name):
    tags = set()

    def bracket(match):
        content = match.group(1).strip()
        found = {tag for tag, pattern in BRACKET_TAGS if pattern.search(content)}
        if found:                        # "(Edição Americana)": a tag, not an edition name
            tags.update(found)
            return " "
        # "[STEELBOOK EDITION]": an edition written in brackets, keep it in the name
        if set(normalize_name(content).split()) & EDITION_END:
            return f" {content} "
        return " "

    text = BRACKETS.sub(bracket, OFFER_SUFFIX.sub("", name))

    for tag, pattern in NAME_TAGS:
        if pattern.search(text):
            tags.add(tag)
            text = pattern.sub(" ", text)

    return text, tags


def split_on_dash(cleaned):
    parts = DASH_SPLIT.split(cleaned)
    if len(parts) < 2:
        return None, None, None

    tail = normalize_name(parts[-1]).split()
    if not tail or tail[-1] not in EDITION_END or len(tail) > 5:
        return None, None, None

    return " - ".join(parts[:-1]), " ".join(tail), parts[-1]


def split_on_words(cleaned, known_phrases):
    tokens = normalize_name(cleaned).split()
    cut = len(tokens)

    # Rule 2: longest known phrase that ends the name
    for phrase in sorted(known_phrases, key=len, reverse=True):
        words = phrase.split()
        if len(tokens) > len(words) and tokens[-len(words):] == words:
            cut = len(tokens) - len(words)
            break
    else:
        # Rule 3: trailing edition words, ending in "edition" or a strong word,
        # or Portuguese order "Edição Standard" / "Edição Gold"
        portuguese = len(tokens) > 2 and tokens[-2] in ("edicao", "versao") and tokens[-1] in EDITION_WORDS
        if tokens and (tokens[-1] in EDITION_END | STRONG_EDITION_WORDS or portuguese):
            while cut > 0 and tokens[cut - 1] in EDITION_WORDS:
                cut -= 1
        if cut > 1 and tokens[cut:] and all(t in EDITION_END for t in tokens[cut:]):
            cut -= 1  # "midnight edition"

    if cut == len(tokens):
        return cleaned, "", ""

    game_title, edition_text = cut_display(cleaned, cut)
    return game_title, " ".join(tokens[cut:]), edition_text


def cut_display(cleaned, n_tokens):
    """Split the original text after its n-th word (as counted by normalize_name)."""
    chunks = cleaned.split()
    count = 0

    for i, chunk in enumerate(chunks):
        if count == n_tokens:
            return " ".join(chunks[:i]).strip(" -–:|/,+"), " ".join(chunks[i:])
        # one chunk can be several words once normalized ("2K26" → "2 k 26")
        count += len(normalize_name(chunk).split())

    return cleaned, ""


def display_case(text):
    """
    An edition's display name, tidied: capitals ("COLLECTOR'S EDITION" → "Collector's Edition"),
    a lost apostrophe ("Collector?s"), "Edition" twice or first ("Edition GOTY" → "GOTY Edition").
    """
    text = (text or "").strip(" -–:|/,+")
    text = string.capwords(text) if text.isupper() else text
    text = re.sub(r"(?<=[A-Za-z])[?�’](?=s\b)", "'", text)
    text = re.sub(r"\b(Edition)(\s+Edition)+\b", r"\1", text, flags=re.IGNORECASE)
    if m := re.fullmatch(r"(Edition|Edição)\s+(.+)", text, flags=re.IGNORECASE):
        text = f"{m.group(2)} {m.group(1)}" if m.group(1).lower() == "edition" else text
    return text


def learn_phrase(name):
    """The edition phrase if `name` uses the "Title - X Edition" form, else None."""
    text, _ = extract_tags(name)
    _, phrase, _ = split_on_dash(clean_name(text))
    return phrase if phrase and phrase not in STANDARD_PHRASES else None
