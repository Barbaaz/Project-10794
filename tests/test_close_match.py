"""Shortened store names → known games (core/close_match.py)."""
from core.close_match import KeyIndex, close_match

KNOWN = {
    "star wars galactic racer", "star wars", "final fantasy vii revelation", "tales of eternia remastered",
    "doom the dark ages", "god of war ragnarok", "god of war laufey", "f 1 manager 23", "resident evil revelations 2",
    "lets sing abba 2027", "paw patrol dino world", "tomb raider legacy of atlantis",
}


def test_shortened_names_find_their_game():
    assert close_match("star war galactic racer", KNOWN) == "star wars galactic racer"   # a word cut short
    assert close_match("tales of eternia remas", KNOWN) == "tales of eternia remastered"  # the last word cut
    assert close_match("ff vii revelation", KNOWN) == "final fantasy vii revelation"     # abbreviation
    assert close_match("doom dark ages", KNOWN) == "doom the dark ages"                  # a linking word left out
    assert close_match("star wars", KNOWN) == "star wars"                                # exact still wins
    assert close_match("legend of zelda breath of the wild",
                       {"the legend of zelda breath of the wild"}) == "the legend of zelda breath of the wild"


def test_different_games_are_never_joined():
    assert close_match("god of war", KNOWN) is None             # the last word must match
    assert close_match("f 1 23", KNOWN) is None                 # "manager" is a real word, not a linking one
    assert close_match("resident evil 2", KNOWN) is None
    assert close_match("lets sing 2027", KNOWN) is None
    assert close_match("paw patrol world", KNOWN) is None
    assert close_match("lets sing 2026", {"lets sing 2027"}) is None    # numbers must be the same
    assert close_match("tomb raider atlantis", KNOWN) is None   # "legacy" missing: not sure enough


def test_several_candidates_means_no_match():
    assert close_match("god of war", {"god of war ragnarok", "god of war laufey"}) is None
    assert close_match("dark ages", {"dark ages i", "dark ages ii"}) is None


def test_one_word_names_are_too_short_to_guess():
    assert close_match("doom", {"doom eternal"}) is None


def test_words_written_together_or_apart_are_the_same_game():
    index = KeyIndex(["spongebob squarepants the cosmic shake", "lego marvel super heroes 2", "nier automata",
                      "resident evil 3 4"])
    assert index.resolve("sponge bob squarepants the cosmic shake") == "spongebob squarepants the cosmic shake"
    assert index.resolve("lego marvel superheroes 2") == "lego marvel super heroes 2"
    assert index.resolve("nierautomata") == "nier automata"
    assert index.resolve("resident evil 34") == "resident evil 34"       # numbers must stay the same
