CARD = "article.product-grid-module"
NAME = "div.mobile > meta[itemprop=name]"                 # "JOGO PS5 CONTROL RESONANT"
LINK = "a[itemprop=url]"
IMAGE = "img[itemprop=image]"                               # the real image is in content="" (src is a 1x1 placeholder)
PRICE = "[itemprop=price]"                                  # content="50.99"
OLD_PRICE = ".old-price"                                    # "strike" = crossed-out price; "PVPR" = recommended retail price
AVAILABILITY = "meta[itemprop=availability]"                # schema.org: PreSale, InStock, OutOfStock...
CONDITION = "meta[itemprop=itemCondition]"                  # schema.org: NewCondition / UsedCondition
PRESALE_DATE = ".flags-item.pre-sale aside"                 # "Lançamento a 15 de outubro de 2026"
