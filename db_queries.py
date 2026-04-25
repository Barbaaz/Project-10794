from db import get_connection

def get_recent_products(query, minutes=10):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT Store, Nome, Console, Preco, PrecoAntigo, EmStock, Url, Imagem
        FROM Produtos
        WHERE Nome LIKE ?
        AND DataRegisto > DATEADD(MINUTE, ?, GETDATE())
    """, f"%{query}%", -minutes)

    rows = cursor.fetchall()
    conn.close()

    products = []

    for r in rows:
        products.append({
            "store": r[0],
            "external_name": r[1],
            "console": r[2],
            "price": r[3],
            "sale": r[4],
            "in_stock": r[5],
            "url": r[6],
            "image": r[7]
        })

    return products

def get_price_history(name, console):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DataRegisto, Preco
        FROM Produtos
        WHERE Nome = ? AND Console = ?
        ORDER BY DataRegisto
    """, name, console)

    rows = cursor.fetchall()
    conn.close()

    return [{"date": str(r[0]), "price": r[1]} for r in rows]