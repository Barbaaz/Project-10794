import pytest

from core.editions import is_excluded, learn_phrase, parse_title
from core.normalizer import normalize_name


@pytest.mark.parametrize("name, game_key, edition_key", [
    ("NBA 2K26 - Kobe Bryant Edition PS5", "nba 2 k 26", "bryant kobe"),   # edition words sorted
    ("Silent Hill: Townfall - Day One Edition PS5", "silent hill townfall", "day one"),
    ("SILENT HILL TOWNFALL DAY ONE EDITION PS5", "silent hill townfall", "day one"),
    ("Silent Hill: Townfall PS5", "silent hill townfall", ""),
    ("CASTLEVANIA Belmonts Curse Midnight Edition PS5", "castlevania belmonts curse", "midnight"),
    ("Assassin's Creed Shadows Game of the Year Edition PS5", "assassins creed shadows", "goty"),
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
    assert (parsed.game_key, parsed.edition_key) == ("nba 2 k 26", "bryant kobe")
    assert parsed.edition_name == "Kobe Bryant Edition"


@pytest.mark.parametrize("a, b", [
    ("Silent Hill f - Day One Steelbook Edition PS5", "Silent Hill f Steelbook Day One Edition PS5"),   # word order
    ("Silent Hill f - Day 1 Edition PS5", "Silent Hill f Day One Edition PS5"),
    ("Assassin's Creed Shadows - GOTY Edition PS5", "Assassin's Creed Shadows Game of the Year Edition PS5"),
    ("Game X - Collector Edition PS5", "Game X - Collector's Edition PS5"),
    ("Game X - The Complete Edition PS5", "Game X - Complete Edition PS5"),
    ("Game X - Physical Deluxe Edition PS5", "Game X - Deluxe Edition PS5"),
    ("Jogo Hogwarts Legacy Edição Deluxe PS5", "Hogwarts Legacy - Deluxe Edition PS5"),
])
def test_same_edition_written_differently(a, b):
    assert parse_title(a).edition_key == parse_title(b).edition_key != ""


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


@pytest.mark.parametrize("name, game_key, edition_key", [
    # Gaming Replay (2026-10-03): a bonus after the name isn't part of the title
    ("Mortal Kombat 1 Switch - Oferta DLC", "mortal kombat 1", ""),
    ("Animal Crossing New Horizons - Nintendo Switch 2 Edition Switch 2 - Oferta Postal", "animal crossing new horizons", ""),
    ("Ofertas Especiais Game - Deluxe Edition PS5", "ofertas especiais game", "deluxe"),
    # regional imports are their own product, tagged like "Import JP"
    ("Capcom Fighting Collection 2 (Edição Americana) Switch", "capcom fighting collection 2", "|Import US"),
    ("Hyke: Northern Light(s) (Edição Asiática) Switch", "hyke northern light", "|Import Asia"),
    ("Food Girls 2: Civil War (Edição Japonesa) Switch", "food girls 2 civil war", "|Import JP"),
])
def test_gaming_replay_names(name, game_key, edition_key):
    parsed = parse_title(name)
    assert (parsed.game_key, parsed.edition_key) == (game_key, edition_key)


def test_coib_is_code_in_box():
    assert is_excluded("Sushi Bar Express (COIB) Switch")
    assert not is_excluded("Coibra Racing PS5")


# Found by the audit of every stored name (2026-10-03)
@pytest.mark.parametrize("name, game_key, edition_key", [
    # "Day 1" before edition words is part of the edition
    ("GAME X DAY 1 STEELBOOK EDITION PS5", "game x", "day one steelbook"),
    # offers written without a dash
    ("BORDERLANDS 3 (EM PORTUGUÊS) Oferta DLC XBOX ONE", "borderlands 3", ""),
    ("MARVEL AVENGERS Com Ofertas PS4", "marvel avengers", ""),
    ("EA Sports FC 24 PS5 - Inclui Update UEFA EURO 2024™", "ea sports fc 24", ""),
    # PlayStation Hits outside brackets is the same tag
    ("RESIDENT EVIL 7 BIOHAZARD HITS PS4", "resident evil 7 biohazard", "|PlayStation Hits"),
    ("Resident Evil 7: Biohazard - PSHits PS4", "resident evil 7 biohazard", "|PlayStation Hits"),
    ("Yakuza 6 The Song Of Life PS Hits PS4", "yakuza 6 the song of life", "|PlayStation Hits"),
    ("Horizon Zero Dawn - Complete Edition - Hits PS4", "horizon zero dawn", "complete|PlayStation Hits"),
    # Portuguese editions get the English keys
    ("SPIDER-MAN Edição Jogo do Ano PS4", "spiderman", "goty"),
    ("Metroid Ravenous Edição Especial - Nintendo Switch 2", "metroid ravenous", "special"),
    ("Jogo Master Detective Archives: RAIN CODE Edição Especial Limitada Nintendo Switch",
     "master detective archives rain code", "limited special"),
    ("Game X Edição de Colecionador PS5", "game x", "collectors"),
    # a leading "Steelbook"
    ("Steelbook Silent Hill: Townfall", "silent hill townfall", "steelbook"),
    # "Xbox One / Series X/S"
    ("Jogo Saints Row - Day One Edition Xbox One / Series X/S", "saints row", "day one"),
])
def test_audit_names(name, game_key, edition_key):
    parsed = parse_title(name)
    assert (parsed.game_key, parsed.edition_key) == (game_key, edition_key)


@pytest.mark.parametrize("a, b", [
    ("Dark Souls III PS4", "DARK SOULS 3 PS4"),
    ("Grand Theft Auto V PS4", "Grand Theft Auto 5 PS4"),
    ("Final Fantasy VII Rebirth PS5", "FINAL FANTASY 7 REBIRTH PS5"),
    ("Warhammer 40,000: Space Marine II PS5", "Warhammer 40,000: Space Marine 2 PS5"),
])
def test_roman_numerals_are_numbers(a, b):
    assert normalize_name(a) == normalize_name(b)


@pytest.mark.parametrize("a, b", [
    ("Tony Hawk's Pro Skater 3+4 PS5", "TONY HAWKS PRO SKATER 3 + 4 PS5"),
    ("Patapon 1+2 Replay Switch", "PATAPON 1 + 2 Replay Switch"),
])
def test_plus_between_numbers_is_a_space(a, b):
    assert normalize_name(a) == normalize_name(b)
    assert normalize_name("Pro Skater 3+4") == "pro skater 3 4"


def test_keys_stored_before_the_plus_rule():
    from core.normalizer import split_plus_numbers

    assert split_plus_numbers("tony hawks pro skater 34", "Tony Hawk's Pro Skater 3+4") == "tony hawks pro skater 3 4"
    assert split_plus_numbers("fifa 34", "FIFA 34") == "fifa 34"              # no "+" in the title: a number


@pytest.mark.parametrize("name", ["Mega Man X Legacy Collection PS4", "Octopath Traveler I PS4", "I Am Bread PS4"])
def test_i_and_x_stay_letters(name):
    assert normalize_name(name).split()[-1] in ("collection", "i", "bread")
    assert not any(w.isdigit() for w in normalize_name(name).split())


def test_special_edition_in_portuguese_is_the_english_one():
    assert parse_title("Game X Edição Especial PS5").edition_key == parse_title("Game X - Special Edition PS5").edition_key
