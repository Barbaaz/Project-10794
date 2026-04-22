from db import get_connection

def insert_products(products):
    conn = None

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.fast_executemany = True

        for p in products:
            cursor.execute("""
                INSERT INTO Produtos
                (Store, Nome, Console, Preco, PrecoAntigo, EmStock, Url, Imagem)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            p.get("store"),
            p.get("external_name"),
            p.get("console"),
            p.get("price"),
            p.get("sale"),
            p.get("in_stock"),
            p.get("url"),
            p.get("image")   # 🔥 NOVO
            )

        conn.commit()

    except Exception as e:
        print("Erro na BD:", e)

    finally:
        if conn:
            conn.close()