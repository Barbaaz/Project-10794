def criar_produto(
    nome,
    consola,
    preco,
    preco_antigo,
    stock,
    loja,
    link
):
    # calcular promoção
    if preco and preco_antigo:
        desconto = round((preco_antigo - preco) / preco_antigo * 100, 2)
        em_promocao = True
    else:
        desconto = 0
        em_promocao = False

    return {
        "nome": nome,
        "consola": consola,
        "preco": preco,
        "preco_antigo": preco_antigo,
        "desconto": desconto,
        "em_promocao": em_promocao,
        "stock": stock,
        "loja": loja,
        "link": link
    }