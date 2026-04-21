import re

def limpar_preco(p):
    if not p:
        return None
    return float(p.replace('€', '').replace(',', '.').strip())


def extrair_consola(nome):
    match = re.search(
        r'\b(PS5|PS4|Xbox One|Xbox Series X|Xbox Series S|Nintendo Switch|Switch)\b',
        nome,
        re.IGNORECASE
    )
    if not match:
        return None

    raw = match.group(1)

    if "PS5" in raw:
        return "PS5"
    elif "PS4" in raw:
        return "PS4"
    elif "Xbox" in raw:
        return "Xbox"
    elif "Switch" in raw:
        return "Switch"

def limpar_nome(nome):
    nome = re.sub(
        r'\b(PS5|PS4|Xbox One|Xbox Series X|Xbox Series S|Nintendo Switch|Switch)\b',
        '',
        nome,
        flags=re.IGNORECASE
    )
    nome = re.sub(r'\b(MP)\b', '', nome, flags=re.IGNORECASE)
    nome = re.sub(r'\s+', ' ', nome)
    return nome.strip()