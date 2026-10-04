"""Possible duplicates by name (core/similar_names.py): pairs found in the real catalogue, 2026-10-04."""
from core.normalizer import normalize_name
from core.similar_names import similar, similar_pairs


def alike(a, b):
    return similar(normalize_name(a), normalize_name(b), a, b)


def test_the_same_game_written_differently():
    assert alike("FATAL FRAME II Crimson Butyerfly Remake", "Fatal Frame II: Crimson Butterfly Remake")    # a typo
    assert alike("Dinasty Warriors 9 Empires", "DYNASTY WARRIORS 9 EMPIRES")
    assert alike("Kingdom Hearts Collection I-III", "KINGDOM HEARTS I-III")
    assert alike("Zelda Breath of the Wild", "The Legend of Zelda: Breath of the Wild")    # one inside the other
    assert alike("Clive Barker's Hellraiser: Revival", "HELLRAISER REVIVAL")
    assert alike("S.T.A.L.K.E.R. 2: Heart of Chornobyl", "S.T.A.L.K.E.R. 2: Heart of Chernobyl")


def test_different_games_stay_apart():
    assert not alike("Taxi Chaos", "Taxi Chaos 2")                               # numbers differ
    assert not alike("Fitness Boxing", "Fitness Boxing 3")
    assert not alike("Xenoblade Chronicles", "Xenoblade Chronicles X")           # a letter
    assert not alike("TOMB RAIDER I-III Remastered", "Tomb Raider IV-VI Remastered")
    assert not alike("Assassin's Creed Odyssey + Valhalla", "Assassin's Creed Odyssey")   # a bundle
    assert not alike("THE SIMS 4", "THE SIMS 4 Expansão GET FAMOUS")             # an expansion
    assert not alike("F1 23", "F1 Manager 23")                                   # a spin-off
    assert not alike("EA Sports FC 26", "EA Sports NHL 26")
    assert not alike("TALES OF BERSERIA Remastered", "TALES OF SYMPHONIA Remastered")


def test_pairs_need_the_same_platform_and_no_different_igdb_entries():
    games = [(1, 5, normalize_name("Withering Rooms"), None, "Withering Rooms"),
             (2, 5, normalize_name("WHITERING ROOMS"), None, "WHITERING ROOMS"),
             (3, 6, normalize_name("Withering Rooms"), None, "Withering Rooms"),                  # another platform
             (4, 5, normalize_name("Captain Toad: Treasure Tracker"), 10, "Captain Toad: Treasure Tracker"),
             (5, 5, normalize_name("CAPTAIN TOAD: TREASURE TREACKER"), 11, "CAPTAIN TOAD: TREASURE TREACKER")]
    assert similar_pairs(games) == [(1, 2)]        # 4 / 5: IGDB already says they're different games
