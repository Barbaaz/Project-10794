import re
from collections import defaultdict

def normalize_name(name):
    name = name.lower()

    # remover conteúdo entre parênteses
    name = re.sub(r"\(.*?\)", "", name)

    # remover ruído comum
    noise_words = [
    "usado", "semi novo", "novo",
    "gold edition", "edition", "deluxe", "bundle",
    "remake", "collection",
    "playstation", "ps5", "ps4", "ps3",
    "xbox one", "xbox series", "xbox",
    "nintendo switch", "switch"
    ]

    for word in noise_words:
        name = name.replace(word, "")

    name = name.replace("  ", " ")

    # remover símbolos
    name = re.sub(r"[^a-z0-9\s]", "", name)

    # normalizar espaços
    name = " ".join(name.split())

    return name