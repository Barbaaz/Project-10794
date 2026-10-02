def deduplicate(products):
    """
    One entry per (url, condition). The same product can show up in two
    categories (e.g. Xbox One and Series X); the first one seen wins.
    """
    unique = {}

    for product in products:
        unique.setdefault((product["url"], product["condition"]), product)

    return list(unique.values())
