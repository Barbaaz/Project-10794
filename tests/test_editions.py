import pytest

from core.editions import is_excluded, learn_phrase, parse_title
from core.normalizer import normalize_name


@pytest.mark.parametrize("name, game_key, edition_key", [
    ("NBA 2K26 - Kobe Bryant Edition PS5", "nba 2 k 26", "kobe bryant"),
    ("Silent Hill: Townfall - Day One Edition PS5", "silent hill townfall", "day one"),
    ("SILENT HILL TOWNFALL DAY ONE EDITION PS5", "silent hill townfall", "day one"),
    ("Silent Hill: Townfall PS5", "silent hill townfall", ""),
    ("CASTLEVANIA Belmonts Curse Midnight Edition PS5", "castlevania belmonts curse", "midnight"),
    ("Assassin's Creed Shadows Game of the Year Edition PS5", "assassins creed shadows", "game of the year"),
    ("BEYOND A STEEL SKY [STEELBOOK EDITION] PS4", "beyond a steel sky", "steelbook"),
    ("NBA 2K25 Standard Edition PS5", "nba 2 k 25", ""),
    ("Pokémon Legends: Z-A Nintendo Switch 2 Edition", "pokemon legends za", ""),
    ("Jogo Street Fighter 6 PS5", "street fighter 6", ""),
    # Tags that make it a different product
    ("Tomb Raider: Legacy of Atlantis - Collector's Edition Game Key Card Nintendo Switch 2",
     "tomb raider legacy of atlantis", "collectors|Game Key Card"),
    # Weak words alone don't make an edition
    ("Halloween: The Game Xbox Series X", "halloween the game", ""),
    ("Persona 5 Royal PS4", "persona 5 royal", ""),
    # Ignored brackets
    ("Barbie Project Friendship [USADO / ES] PS4", "barbie project friendship", ""),
])
def test_parse_title(name, game_key, edition_key):
    parsed = parse_title(name)
    assert (parsed.game_key, parsed.edition_key) == (game_key, edition_key)


def test_deluxe_and_deluxe_edition_are_the_same_edition():
    a, b = parse_title("Hogwarts Legacy Deluxe PS5"), parse_title("HOGWARTS LEGACY DELUXE EDITION PS5")
    assert (a.game_key, a.edition_key) == (b.game_key, b.edition_key) == ("hogwarts legacy", "deluxe")


def test_phrase_learned_from_dash_names_splits_names_without_dash():
    known = {learn_phrase("NBA 2K26 - Kobe Bryant Edition PS5")}
    parsed = parse_title("NBA 2K26 KOBE BRYANT EDITION PS5", known)
    assert (parsed.game_key, parsed.edition_key) == ("nba 2 k 26", "kobe bryant")
    assert parsed.edition_name == "Kobe Bryant Edition"


def test_display_names():
    parsed = parse_title("Call of Duty Modern Warfare 4 + Steelbook PS5")
    assert parsed.game_title == "Call of Duty Modern Warfare 4"
    assert parsed.edition_name == "Steelbook"
    assert parse_title("Marvel's Spider-Man 2 PS5").edition_name == "Standard"


@pytest.mark.parametrize("a, b", [
    ("Pokémon Legends: Z-A - Nintendo Switch 2 Edition", "POKEMON LEGENDS Z-A SWITCH 2"),
    ("Marvel's Spider-Man 2 PS5", "MARVEL'S SPIDER-MAN 2 (PT) PS5"),
    ("EA Sports FC 27 Xbox One / Series X", "EA SPORTS FC 27 XBOX ONE | X|S"),
    ("Far Cry 3 [USADO] PS3", "FAR CRY 3 PS3"),
    # reported 2026-10-02: same edition listed twice
    ("Metal Gear Solid: Master Collection Vol.2 - Day One Edition PS5",
     "Metal Gear Solid: Master Collection Vol. 2 Day One Edition PS5"),
    ("METAL GEAR SOLID Master Collection Vol.1 PS5", "Metal Gear Solid: Master Collection Vol. 1 PS5"),
    ("NBA2K25 PS5", "NBA 2K25 PS5"),
])
def test_same_game_from_different_stores_normalizes_the_same(a, b):
    assert normalize_name(a) == normalize_name(b)


@pytest.mark.parametrize("name, excluded", [
    ("EA Sports FC 26 [CÓDIGO NA CAIXA] PS5", True),
    ("EA SPORTS FC 26 (CODE IN BOX) PS5", True),
    ("Game [Código de descarga] PS5", True),
    ("Call of Duty Black Ops Cold War (COD) Xbox One", True),
    ("THE SIMS 4 Expansão GET TOGETHER [Download Digital] PC", True),
    ("Some Game (Código Digital) PS5", True),
    ("Digital Deluxe Edition PS5", False),
    ("Call of Duty: Black Ops 7 PS5", False),
    ("Codename Kids Next Door PS5", False),
])
def test_codigo_na_caixa_is_excluded(name, excluded):
    assert is_excluded(name) == excluded
