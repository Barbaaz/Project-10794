"""Which store products are consoles, controllers or headsets, and how they group (core/hardware.py)."""
import pytest

from core.hardware import display_name, hardware_key, kind_of


@pytest.mark.parametrize("name, page, kind", [
    ("Consola PlayStation 5 Slim Digital Edition 1TB", "console", "console"),
    ("Bundle Consola Nintendo Switch 2 + Nintendo Switch Sports Resort + 3 Meses NSO", "console", "console"),
    ("Consola Xbox Series X 1TB + 2 Comandos", "console", "console"),             # a bundle is a console
    ("Nintendo Switch OLED Branca", "console", "console"),                         # console page, no "consola"
    ("Comando sem fios DualSense Playstation 5 Edição Especial Icon Blue", "accessory", "controller"),
    ("Comando GEARS OF WAR EDAY Limited Edition Xbox Series X", "accessory", "controller"),
    ("Joy-Con (L)/(R) Pastel Purple/Green", "accessory", "controller"),
    ("Volante Logitech G923 + Pedais PS5", "accessory", "controller"),
    ("Auscultadores Gaming Turtle Beach Stealth 600 Gen 3", "accessory", "headset"),
    ("Headset Pulse Elite PS5", "accessory", "headset"),
    ("PlayStation VR2", "accessory", "headset"),
    ("Headset com microfone HyperX Cloud II", "accessory", "headset"),
    # small accessories, chairs, PC parts and merchandise: left out
    ("Estação de Carregamento DualSense", "accessory", None),
    ("Bolsa de transporte e protetor de ecrã Nintendo Switch 2 Zelda 40th Anniversary", "console", None),
    ("Cabo USB-C 3m PS5", "accessory", None),
    ("Cartão de Memória Expansão 1TB Xbox Series", "accessory", None),
    ("Suporte para Headset", "accessory", None),
    ("Cadeira Gaming Playseat PS5", "accessory", None),
    ("Thumb Grips Comando PS5", "accessory", None),
    ("Figura Banpresto One Piece Shanks", "accessory", None),
    ("Capa Comando PS5 Silicone", "accessory", None),
    ("Pilhas Kodac Zinco C LR14 (Pack 2)", "accessory", None),
    ("Câmara HD PS5", "accessory", None),                                           # nothing we keep says so
    # from Press Start's pages (2026-10-07)
    ("Volante Thrustmaster T598 Racing Wheel + Servo Base + Pedais (PS4 / PS5 / PC)", "accessory", "controller"),
    ("Joystick Thrustmaster - T.Flight Hotas 5 (PC / PS4 / PS5)", "accessory", "controller"),
    ("Split Pad Pro Hori Pikachu & Eevee Nintendo Switch", "accessory", "controller"),
    ("Hori 3D Surround Gaming Neckset - PS5/PS4/PC", "accessory", "headset"),
    ("Nintendo Switch Joy-Con Wheel (Set 2 Volantes)", "accessory", None),
    ("Oniverse Pack 2 Racing Wheels - Nintendo Switch 2 (Orange / Blue)", "accessory", None),
    ("Volante Joy-Con XL FR-TEC - Nintendo Switch", "accessory", None),
    ("Conjunto Joy-Con Strap (Esquerdo / Direito) Azul Claro", "accessory", None),
    ("PS5 Dualsense Silicon Pad Cover - Real Madrid (Blue)", "accessory", None),
    ("Comando PS5 Dualsense Combo Pack - Rick & Morty", "accessory", None),
    ("Conjunto Comandos Joy-Con Nintendo Switch - Rosa Pastel", "accessory", "controller"),
    ("Joy-Con Nintendo Switch Direito: Under Control - iicon Blue (Dragonne V3 with Strap)", "accessory", "controller"),
    ("Indeca Straps Set - Nintendo Switch", "accessory", None),
    # from Gaming Replay's: what follows a "+" comes with it
    ("Comando sem fios DualSense Playstation 5 - Midnight Black + Cabo USB-C (Comp. PC/MAC)", "accessory", "controller"),
    ("Nintendo Switch Pro Controller + cabo USB", "accessory", "controller"),
    ("STEALTH Premium Travel Kit - Nintendo Switch (Bolsa + Headset + Cabo)", "accessory", None),
    ("Capa de Silicone + Grips (Azul) joy-con direito Switch", "accessory", None),
    ("Sponge Rings + Grips Woxter - Comando PS4", "accessory", None),
    # from Mega Mania's
    ("HORI Fighting Stick Mini PS4", "accessory", "controller"),
    ("MÓDULO MANÍPULO DUALSENSE EDGE PS5", "accessory", None),
])
def test_kind_of(name, page, kind):
    assert kind_of(name, page) == kind


def test_the_same_product_from_two_stores_has_one_key():
    a = hardware_key("Comando sem fios DualSense PS5 Branco", "controller")
    b = hardware_key("DualSense Wireless Controller - White (PlayStation 5)", "controller")
    assert a == b == "controller:dualsense white"
    assert hardware_key("Consola PS5 Slim Digital 1TB", "console") == \
        hardware_key("PlayStation 5 Slim Digital Edition 1 TB Consola", "console") == "console:1 digital slim tb"
    assert hardware_key("Comando Edição Limitada Gears", "controller") == hardware_key("Gears Limited Edition Controller", "controller")


def test_different_models_stay_apart():
    """Strict: Slim vs Pro, digital vs disc, colours, kinds."""
    assert hardware_key("Consola PS5 Slim Digital", "console") != hardware_key("Consola PS5 Slim", "console")
    assert hardware_key("Consola PS5 Pro", "console") != hardware_key("Consola PS5 Slim", "console")
    assert hardware_key("Comando DualSense Preto", "controller") != hardware_key("Comando DualSense Branco", "controller")
    assert hardware_key("PlayStation VR2", "headset").startswith("headset:")
    # colours in brackets, wired vs wireless
    assert hardware_key("Comando Subsonic LED RGB (Branco)", "controller") != hardware_key("Comando Subsonic LED RGB (Preto)", "controller")
    assert hardware_key("Comando Raptor PS4 (com fios)", "controller") != hardware_key("Comando Raptor PS4 Wireless (sem fios)", "controller")


def test_colours_however_written():
    assert hardware_key("Turtle Beach Recon 50 Preto/Vermelho", "headset") == hardware_key("Turtle Beach Recon 50 Black Red", "headset")
    assert hardware_key("FUYIN 2 Vermelhos", "headset") == hardware_key("Fuyin 2 Red", "headset")
    assert hardware_key("NACON COMPACT Com Fio Azul PS4", "controller") == "controller:blue compact nacon wired"


def test_a_hardware_page_keeps_consoles_controllers_and_headsets():
    """BaseScraper.keep_hardware: the kind, the platform the name says, consoles that name their platform."""
    from scrapers.base.base_scraper import BaseScraper

    scraper = BaseScraper()
    product = lambda name, console: {"external_name": name, "console": console}
    kept = scraper.keep_hardware([
        product("Consola Nintendo Switch 2", "Switch2"),
        product("Consola THE SPECTRUM (Retro)", "PS5"),                  # listed on the PS5 page: not a PS5
        product("Comando Nintendo Switch Snakebyte Wireless", "Switch2"),   # the name says Switch
        product("Cabo USB-C PS5", "PS5"),
        product("Headset Gioteck XH-100S", "PS4"),
        product("Comando PS3 Sixaxis", "PS3"),                            # an older platform
    ], "console")
    assert [(p["external_name"], p["kind"], p["console"]) for p in kept] == [
        ("Consola Nintendo Switch 2", "console", "Switch2"),
        ("Comando Nintendo Switch Snakebyte Wireless", "controller", "Switch"),
        ("Headset Gioteck XH-100S", "headset", "PS4"),
    ]
    assert scraper.hardware_left_out == ["Consola THE SPECTRUM (Retro)", "Cabo USB-C PS5", "Comando PS3 Sixaxis"]


def test_the_plain_model_is_standard():
    assert hardware_key("Consola Nintendo Switch 2", "console") == "console:standard"
    assert hardware_key("Consola Sony PlayStation PS5 - Edição Standard", "console") == "console:standard"


def test_display_name():
    assert display_name("Comando DualSense [USADO] (PT)") == "Comando DualSense"
