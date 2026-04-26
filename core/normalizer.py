import re
from collections import defaultdict

def normalize_name(name):
    name = name.lower()

    # remover conteúdo entre parênteses
    name = re.sub(r"\(.*?\)", "", name)

    # remover ruído comum
    noise_words = [
    "usado", "semi novo", "novo",
    # "gold edition", "deluxe", "bundle",
    # "remake", "collection",
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

# VARIANT_KEYWORDS = ['deluxe', 'gold', 'ultimate', 'goty', 'remake', 'remaster', 'remastered']

# def normalize_name(name):
#     name = name.lower()

#     name = re.sub(r'\(,*?\)', "", name)

#     variant = 'standard'
#     for v in VARIANT_KEYWORDS:
#         if v in name:
#             variant = v
#             break
    
#     noise_words = [
#         'playstation', 'ps5', 'ps4', 'ps3',
#         'xbox one', 'xbox series', 'xbox',
#         'nintendo switch', 'switch'
#     ]

#     for word in noise_words:
#         name = name.replace(word, '')

#     name = re.sub(r'[^a-z0-9\s]', '', name)

#     for v in VARIANT_KEYWORDS:
#         name = name.replace(v, '')
    
#     name = ' '.join(name.split())

#     return name, variant