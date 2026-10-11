"""Which spelling of a game to show (core/titles.py): cases from a rematch dry run on the real catalogue, 2026-10-11."""
from core.titles import best_title, flaws


def test_a_better_written_name_wins():
    assert best_title("CRYSIS Remastered", {"CRYSIS Remastered": 1, "Crysis Remastered": 1}) == "Crysis Remastered"
    assert best_title("Lords of The Fallen", {"LORDS OF THE FALLEN": 1, "Lords of the Fallen": 1}) == "Lords of the Fallen"
    assert best_title("Fifa 23", {"FIFA 23": 1}, "FIFA 23") == "FIFA 23"
    assert best_title("Sid Meiers CIVILIZATION VII", {"Sid Meier's Civilization VII": 1}) == "Sid Meier's Civilization VII"


def test_the_current_name_stays_unless_clearly_better():
    # the old rule: the most common, ties alphabetically
    assert best_title("FIFA 23", {"FIFA 23": 1, "FIFA® 23": 1}, "FIFA 23") == "FIFA 23"
    assert best_title("Oddworld: Soulstorm", {"Oddworld: Soulstorm": 1, "Oddworld Soulstorm": 2}) == "Oddworld: Soulstorm"
    assert best_title("Way of the Hunter 2", {"Way Of The Hunter 2": 2, "Way of the Hunter 2": 1}) == "Way of the Hunter 2"
    assert best_title("FINAL FANTASY VII Remake Intergrade",
                      {"FINAL FANTASY VII Remake Intergrade": 1, "Final Fantasy Vii Remake Intergrade": 1}) == \
        "FINAL FANTASY VII Remake Intergrade"
    assert best_title("Ghost of Yōtei", {"Ghost of Yotei": 3}, "Ghost of Yotei") == "Ghost of Yōtei"      # accents stay
    # extra punctuation alone is no reason ("Persona 3 - Reload", "Call of Duty : WWII")
    assert best_title("Persona 3 Reload", {"Persona 3 - Reload": 2}) == "Persona 3 Reload"


def test_igdb_name_breaks_ties():
    assert best_title("Ys x Proud Nordics", {"Ys X: Proud Nordics": 1}, "Ys X: Proud Nordics") == "Ys X: Proud Nordics"
    assert best_title("Ys x Proud Nordics", {"Ys X: Proud Nordics": 1}) == "Ys x Proud Nordics"   # no IGDB name: kept
    # one character closer is not clearly closer
    assert best_title("Watch Dogs Legion", {"Watch Dogs: Legion": 1}, "Watch Dogs: Legion") == "Watch Dogs Legion"


def test_flaws():
    assert flaws("The Legend of Zelda: Breath of the Wild") == 0
    assert flaws("THE LEGEND OF ZELDA") > flaws("FINAL FANTASY VII Remake") > flaws("CRYSIS Remastered") > 0
    assert flaws("FIFA 23") == flaws("LEGO Worlds") == 0                 # short names in capitals are names
    assert flaws("FIFA® 23") == flaws("Trails In The Sky 1St Chapter") - 2 == 1
    assert flaws("Dreamworks Gabby'S Dollhouse") == 1
    assert flaws("Luck Be A Landlord") == 1                              # "A" inside the title
