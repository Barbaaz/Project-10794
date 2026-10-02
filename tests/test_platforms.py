import pytest

from app.utils.utils import detetar_plataforma, extrair_consola


@pytest.mark.parametrize("name, category, expected", [
    # Switch 2 must not be read as Switch
    ("Pokémon Legends Z-A Nintendo Switch 2 Edition", None, "Switch2"),
    ("Mario Kart World Switch 2", None, "Switch2"),
    ("Zelda Nintendo Switch", None, "Switch"),
    ("Switchblade PS4", None, "PS4"),
    # The store category wins over the name...
    ("BEYOND A STEEL SKY PS4 | PS5", "PS4", "PS4"),
    # ...except between the two Xboxes, where the name is more precise
    ("11-11 MEMORIES RETOLD XBOX ONE", "XboxSeries", "XboxOne"),
    ("RAINBOW SIX EXTRACTION XBOX ONE | X|S", "XboxOne", "XboxSeries"),
    ("Fifa 15 Ultimate Team Edition", "XboxOne", "XboxOne"),
    # Cross-gen discs count as Series X|S
    ("EA Sports FC 27 Xbox One / Series X", None, "XboxSeries"),
    ("Elden Ring: Nightreign Xbox One & Series X", None, "XboxSeries"),
    ("Call of Duty: Modern Warfare 4 Xbox Series", None, "XboxSeries"),
    # A name that only says "Xbox"
    ("Street Fighter 6 Lenticular Edition Xbox", None, "XboxSeries"),
    ("Cities Skylines PC", None, "PC"),
    ("Comando DualSense", None, None),
])
def test_detetar_plataforma(name, category, expected):
    assert detetar_plataforma(name, category) == expected


def test_extra_texts_are_used_when_the_name_has_no_platform():
    # CSTech: product_type "Jogos PC" / "Jogos Nintendo Switch 2"
    assert detetar_plataforma("Cities: Skylines II", None, "Jogos PC") == "PC"
    assert extrair_consola("Pikmin", "Jogos Nintendo Switch 2") == "Switch2"
