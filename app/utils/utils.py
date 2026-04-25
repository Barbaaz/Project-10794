import re

def extrair_consola(nome):
    match = re.search(
        r'\b(PS5|PS4|PS3|Xbox One|Xbox Series X|Xbox Series S|Nintendo Switch|Switch)\b',
        nome,
        re.IGNORECASE
    )
    if not match:
        return None

    raw = match.group(1)

    if "ps5" in raw.lower():
        return "PS5"
    elif "ps4" in raw.lower():
        return "PS4"
    elif "ps3" in raw.lower():
        return "PS3"
    elif "xbox" in raw.lower():
        return "Xbox"
    elif "switch" in raw.lower():
        return "Switch"