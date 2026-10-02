import re
from urllib.parse import urljoin

USED_PATTERN = re.compile(r"\b(usado|usada|semi[\s-]?novo|seminovo|pre[\s-]?owned)\b", re.IGNORECASE)


def parse_price(price_text):
    """
    Ex:
    "59,99 €"     → 59.99
    "€39.99"      → 39.99
    "1.299,99 €"  → 1299.99
    "19,99 - 29,99 €" → 19.99
    """
    if price_text is None:
        return None

    text = str(price_text).split("-")[0]
    text = re.sub(r"[^\d,.]", "", text)

    if not text:
        return None

    # The last separator is the decimal one; the other is a thousands separator
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")

    # "1.299.99" → keep only the last dot
    if text.count(".") > 1:
        head, _, tail = text.rpartition(".")
        text = head.replace(".", "") + "." + tail

    return round(float(text), 2)


def detect_condition(*texts):
    """'used' if any text mentions usado / semi-novo, otherwise 'new'."""
    for text in texts:
        if text and USED_PATTERN.search(text):
            return "used"
    return "new"


def absolute_url(base_url, url):
    if not url:
        return None
    return urljoin(base_url, url)
