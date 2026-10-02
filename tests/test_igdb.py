"""Choosing the IGDB entry for a game (no network)."""
import json

from pipeline.igdb import best_match, game_info


def test_prefers_the_main_game_over_editions_and_dlc():
    results = [
        {"id": 2, "name": "Hogwarts Legacy: Dark Arts Pack", "game_type": 13},
        {"id": 3, "name": "Hogwarts Legacy: Deluxe Edition", "game_type": 0, "version_parent": 1},
        {"id": 1, "name": "Hogwarts Legacy", "game_type": 0},
    ]
    assert best_match("hogwarts legacy", results)["id"] == 1


def test_no_match_when_names_differ():
    assert best_match("halloween the game", [{"id": 9, "name": "Halloween Party Games", "game_type": 0}]) is None
    assert best_match("anything", []) is None


def test_names_written_differently_still_match():
    assert best_match("metal gear solid master collection vol 2",
                      [{"id": 5, "name": "Metal Gear Solid: Master Collection Vol.2", "game_type": 0}])["id"] == 5


def test_one_name_inside_the_other():
    # our name lost part of the title to the edition splitter
    assert best_match("rayman 30 th", [{"id": 4, "name": "Rayman: 30th Anniversary Edition", "game_type": 3}])["id"] == 4
    # CSTech's long name around IGDB's short one
    assert best_match("formula one f 1 23", [{"id": 6, "name": "F1 23", "game_type": 0}])["id"] == 6
    assert best_match("fallout 4 goty", [{"id": 8, "name": "Fallout 4", "game_type": 0}])["id"] == 8
    # too short to trust
    assert best_match("halo", [{"id": 1, "name": "Halo Infinite", "game_type": 0}]) is None


def test_title_variants():
    from pipeline.igdb import title_variants
    assert title_variants("Formula One - F1 23") == ["Formula One - F1 23", "F1 23", "Formula One", "formula one f 1 23"]
    assert "Fallout 4 GOTY" in title_variants("Fallout 4 GOTY: 25th Anniversary")


def test_game_info():
    info = game_info({
        "id": 7, "name": "Silent Hill: Townfall", "summary": "Fog.", "first_release_date": 1767225600,
        "genres": [{"name": "Adventure"}, {"name": "Horror"}],
        "involved_companies": [
            {"company": {"name": "Konami"}, "publisher": True, "developer": False},
            {"company": {"name": "Screen Burn"}, "publisher": False, "developer": True},
        ],
        "age_ratings": [{"organization": {"name": "ESRB"}, "rating_category": {"rating": "M"}},
                        {"organization": {"name": "PEGI"}, "rating_category": {"rating": "16"}}],
        "cover": {"image_id": "co123"}, "screenshots": [{"image_id": "sc1"}, {"image_id": "sc2"}],
        "total_rating": 77.4,
    })
    assert info["genres"] == "Adventure, Horror"
    assert (info["publishers"], info["developers"]) == ("Konami", "Screen Burn")
    assert (info["pegi"], info["rating"], info["first_release_date"]) == ("16", 77, "2026-01-01")
    assert json.loads(info["screenshot_ids"]) == ["sc1", "sc2"]
