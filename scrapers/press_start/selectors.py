PRODUCT_CARD = "article.product-miniature.js-product-miniature"
NAME = ".product-title a"
IMAGE = ".thumbnail img"
PRICE = ".product-price-and-shipping .price"            # price the customer pays
PRICE_VALUE = "[itemprop=price]"                         # same price, as "54.99" in content=""
OLD_PRICE = ".product-price-and-shipping .regular-price" # crossed-out price, only when on sale
LINK = "a.thumbnail.product-thumbnail"
STOCK = ".circle-semaphore"                              # full-stock / medium-stock / low-stock (= sold out)
PREORDER_FLAG = ".product-flag.pslabel-pre-reserva"      # "PRÉ-RESERVA"
# Product page only:
#   release date in the text: "Data prevista de lançamento: 2026-12-31"
DESCRIPTION = "#description .product-description"       # full description ("Conteúdo da Collector's Edition: - ...")
DESCRIPTION_SHORT = "#product-description-short"        # fallback
