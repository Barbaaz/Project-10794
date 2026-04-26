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
        exists = any(
            x["store"] == product["store"] and x["price"] == product["price"]
            for x in groups[key]
        )

        if not exists:
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

# def build_key(product):
#     name, variant = normalize_name(product.get("external_name", ""))
#     console = product.get("console", "unknown")

#     return f"{name}_{console}", variant

# def match_products(all_products):
    
#     groups = defaultdict(lambda: defaultdict(list))

#     for product in all_products:
#         key, variant = build_key(product)

#         if not product.get("price"):
#             continue

#         groups[key][variant].append(product)
        
#         exists = any(
#             x['store'] == product['store'] and x['price'] == product['price']
#             for x in groups[key][variant]
#         )

#         if not exists:
#             groups[key][variant].append(product)

#     result = []

#     for key, variants in groups.items():
#         name, console = key.rsplit("_", 1)

#         variant_list = []

#         for variant, items in variants.items():
#             if not items:
#                 continue

#             items = sorted(items, key=lambda x: x["price"] or 9999)

#             variant_list.append({
#                 "type": variant,
#                 "offers": items
#             })

#             result.append({
#                 "name": name,
#                 "console": console,
#                 "offers": [offer for v in variants.values() for offer in v],
#                 "variants": variant_list
#             })

#     return result