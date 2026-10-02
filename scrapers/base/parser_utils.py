import re
from datetime import date
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


MONTHS_PT = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def parse_release_date(text):
    """
    "15 Outubro 2026" / "2026-12-31" / "31/12/2026" → date, or None.
    """
    if not text:
        return None

    try:
        if m := re.search(r"(\d{4})-(\d{2})-(\d{2})", text):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if m := re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text):
            return date(int(m[3]), int(m[2]), int(m[1]))
        if m := re.search(r"(\d{1,2})\s+(?:de\s+)?([a-zç]+)\s+(?:de\s+)?(\d{4})", text.lower()):
            month = MONTHS_PT.get(m[2])
            return date(int(m[3]), month, int(m[1])) if month else None
    except ValueError:   # e.g. 31/02
        return None

    return None


def absolute_url(base_url, url):
    if not url:
        return None
    return urljoin(base_url, url)
