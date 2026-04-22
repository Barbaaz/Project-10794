from collections import defaultdict
from core.normalizer import normalize_name

def build_key(product):
    name = normalize_name(product.get("external_name", ""))
    console = product.get("console", "unknown")

    return f"{name}_{console}"

def match_products(all_products):
    groups = defaultdict(list)

    for product in all_products:
        key = build_key(product)
        if not product.get("price"):
            continue
        groups[key].append(product)

    # NOVO: transformar para lista organizada
    result = []

    for key, items in groups.items():
        if not items:
            continue

        # ordenar por preço
        items = sorted(items, key=lambda x: x["price"] or 9999)

        result.append({
            "name": items[0]["external_name"],
            "console": items[0]["console"],
            "offers": items
        })

    return result