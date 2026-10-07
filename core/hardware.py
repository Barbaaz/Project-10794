"""
Consoles, controllers and headsets the stores sell, next to their games (user, 2026-10-07: those kinds
only; no small accessories such as cases, cables, chargers or memory cards, no chairs, no PC
peripherals, no merchandise).

    kind_of("Comando sem fios DualSense PS5 Branco", "accessory")   → "controller"
    kind_of("Estação de carregamento DualSense", "accessory")       → None (a small accessory)
    hardware_key("Comando DualSense Wireless Controller PS5 Branco", "controller") → "controller:dualsense white"

A product is the same in two stores only when its cleaned name is the same (strict, user's choice):
moderators merge the rest in /admin, as they do for games.
"""
import re
import unicodedata

from core.normalizer import normalize_name

KINDS = ("console", "controller", "headset")

# The platforms a store's hardware is kept for (older ones only for games)
PLATFORMS = {"PS5", "PS4", "Switch2", "Switch", "XboxSeries", "XboxOne"}


def _plain(text):
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _words(*patterns):
    return re.compile(r"\b(?:" + "|".join(patterns) + r")\b")


# Never kept, whatever else the name says: small accessories, chairs, PC parts, merchandise
NOT_KEPT = _words(
    r"carregador\w*", r"carregamento", r"charg\w*", r"carga", r"cabos?", r"cables?", r"capas?", r"cases?",
    r"bolsas?", r"malas?", r"estojos?", r"protetor\w*", r"protector\w*", r"peliculas?", r"vidro temperado",
    r"suportes?", r"stands?", r"docks?", r"dockings?", r"grips?", r"thumb\w*", r"skins?", r"covers?",
    r"joy-?con straps?", r"straps? set", r"faceplates?", r"custom kit", r"combo pack",   # (Joy-Cons "with Strap" stay)
    # plastic wheels to put a Joy-Con in, sold in sets: not steering wheels
    r"joy-?con (?:2 )?wheels?", r"volantes? joy-?con", r"racing wheels", r"wheel set", r"\d+ volantes",
    r"pack \d+ racing wheels?",
    r"autocolantes?", r"stickers?", r"adaptador\w*", r"adapters?", r"baterias?", r"batter\w*", r"pilhas",
    r"cart(?:ao|oes)", r"memoria", r"memory", r"microsd",
    r"cadeiras?", r"chairs?", r"secretarias?", r"teclados?", r"keyboards?", r"ratos?", r"mouse\w*",
    r"tapetes?", r"webcams?",
    r"figuras?", r"funko", r"porta[ -]chaves", r"canecas?", r"t-?shirts?", r"camisolas?",
    r"mochilas?", r"posters?", r"bones?", r"kits?", r"packs? de acessorios", r"acessorios para",
    r"replacement", r"substitui\w*", r"pecas?", r"botoes", r"joysticks? de substituicao", r"modulos?",
    r"gift ?cards?", r"cartao presente", r"subscri\w*", r"assinatura",
)
CONTROLLER = _words(
    r"comandos?", r"controllers?", r"controladores?", r"dualsense", r"dualshock", r"joy-?cons?",
    r"gamepads?", r"volantes?", r"wheels?", r"pedais", r"pedals?", r"arcade ?sticks?", r"fight ?sticks?",
    r"flight ?sticks?", r"fighting ?sticks?", r"joysticks?", r"hotas", r"split ?pads?",
)
HEADSET = _words(
    r"auscultador\w*", r"headsets?", r"headphones?", r"auriculares?", r"earbuds?", r"necksets?",
    r"playstation vr\w*", r"ps ?vr\w*", r"vr ?2", r"realidade virtual",
)
CONSOLE = _words(r"consolas?", r"consoles?")


def kind_of(name, page="accessory"):
    """
    The product's kind (KINDS), or None when it isn't one we keep. `page` is the kind of store
    page it was listed on: "console" pages also carry bundles and the odd bag; "accessory" pages
    carry everything else (controllers, headsets, and the small accessories we leave out).
    """
    # after a "+" come the extras: "DualSense + Cabo USB-C" is a controller, "Base de Carregamento + …" isn't,
    # nor "Sponge Rings + Grips - Comando PS4": the product is what comes before it
    text = _plain(name).split(" + ")[0]
    if NOT_KEPT.search(text):
        return None
    if HEADSET.search(text):
        return "headset"
    if CONSOLE.search(text) and (page == "console" or not CONTROLLER.search(text)):
        return "console"       # "Consola PS5 + 2 comandos" is a console bundle
    if CONTROLLER.search(text):
        return "controller"
    return "console" if page == "console" else None


# Words left out of the key: what the kind already says, and filler
KEY_FILLER = {
    "consola", "consolas", "console", "consoles", "comando", "comandos", "controller", "controllers",
    "controlador", "auscultadores", "auscultador", "headset", "headphones", "gaming", "jogos", "jogo",
    "sem", "fios", "wireless", "de", "da", "do", "das", "dos", "para", "com", "e", "o", "a", "the",
    "for", "with", "and", "oficial", "official", "nintendo", "sony", "microsoft",
    "edition",          # "Digital Edition" = "Digital"; "Edição Limitada" = "Limited Edition" = "limited"
    "multiplataforma", "multiplatform", "multi", "plataforma",
}
# Portuguese and English spellings of the same thing
KEY_WORDS = {
    "edicao": "edition", "limitada": "limited", "especial": "special", "padrao": "standard", "terabyte": "tb",
    "camuflado": "camo", "camoflado": "camo", "camouflage": "camo", "metalico": "metallic", "metalizado": "metallic",
    "transparente": "transparent", "gray": "grey",
}
# Colours, in Portuguese (any gender / number) and English
for colour, words in {
    "white": "branco branca brancos brancas", "black": "preto preta pretos pretas negro negra",
    "grey": "cinzento cinzenta cinzentos cinza", "blue": "azul azuis", "red": "vermelho vermelha vermelhos vermelhas",
    "green": "verde verdes", "pink": "rosa rosas", "purple": "roxo roxa roxos", "yellow": "amarelo amarela amarelos",
    "orange": "laranja laranjas", "lilac": "lilas", "gold": "dourado dourada", "silver": "prateado prateada",
}.items():
    KEY_WORDS.update(dict.fromkeys(words.split(), colour))


def hardware_key(name, kind):
    """
    The key that groups the same product across stores: its kind, then the cleaned name's words
    sorted (stores order them differently), without filler, platform or condition
    ("controller:dualsense white").
    """
    # brackets are part of it here ("(Branco)", "(com fios)", "(Caixa Danificada)": another product);
    # wired is a different product, wireless is what a name usually leaves out
    name = re.sub(r"[\[\]()/|]", " ", name)          # "Preto/Azul" is two words
    name = re.sub(r"\bcom\s+fios?\b", " wired ", name, flags=re.IGNORECASE)
    words = {KEY_WORDS.get(w, w) for w in normalize_name(name).split()} - KEY_FILLER
    return f"{kind}:{' '.join(sorted(words)) or 'standard'}"     # "Consola Nintendo Switch 2": the standard model


def display_name(name):
    """The store's name for showing, without brackets ("[USADO]", "(PT)") and extra spaces."""
    return " ".join(re.sub(r"[\(\[].*?[\)\]]", " ", name).split()).strip(" -–:|/,&") or name
