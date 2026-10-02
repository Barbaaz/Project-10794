"""
Demo marketplace: a few made-up users with listings and conversations at every purchase
step, to see how the marketplace looks. Everything is made through the same services real
users go through, so the rules apply. Photos are generated (marked DEMO), nothing downloaded.

    python -m database.demo_market            # add the demo (again: replaces it)
    python -m database.demo_market --remove   # remove it (users, listings, chats, photo files)

Log in as any of them with the password DEMO_PASSWORD (e.g. demo_ana / demo12345).
Demo users are recognised by their username prefix "demo_" and @demo.invalid email.
"""
import argparse
import io
import logging
import random

from PIL import Image, ImageDraw, ImageFont

from app.services import auth_service, chat_service, listing_service
from app.services.photo_storage import storage
from db import connection, fetch_all

log = logging.getLogger(__name__)

DEMO_PASSWORD = "demo12345"
USERS = [
    ("demo_ana", "Ana Ribeiro"), ("demo_bruno", "Bruno Costa"), ("demo_carla", "Carla Mendes"),
    ("demo_diogo", "Diogo Pires"), ("demo_eva", "Eva Santos"),
]
DESCRIPTIONS = [
    "Jogado uma vez, como novo. Com caixa e manual.",
    "Disco sem riscos. Envio por CTT ou entrega em mão em Lisboa.",
    "Ainda selado, recebi em duplicado.",
    "Caixa com um pequeno risco na capa, o disco está impecável.",
    "Vendo porque já terminei. Entrego no Porto ou envio à cobrança.",
    "Edição completa, inclui o código de DLC (não usado).",
]
LISTINGS = 15
GAMES = 9            # 15 listings over 9 games: some games have two sellers
CONDITION_SHARE = {"new": 0.95, "like_new": 0.80, "good": 0.70, "fair": 0.55, "poor": 0.40}
DEMO_USERS = "username LIKE 'demo[_]%' AND email LIKE '%@demo.invalid'"   # never a real user


def remove():
    users = [r["id"] for r in fetch_all(f"SELECT id FROM users WHERE {DEMO_USERS}")]
    if not users:
        log.info("No demo marketplace data")
        return
    ids = ",".join(map(str, users))
    keys = [k for r in fetch_all(
        f"SELECT lp.photo_key, lp.thumb_key FROM listing_photos lp JOIN user_listings l ON l.id = lp.listing_id "
        f"WHERE l.user_id IN ({ids})") for k in (r["photo_key"], r["thumb_key"])]
    with connection() as conn:
        c = conn.cursor()
        conversations = f"SELECT id FROM conversations WHERE buyer_id IN ({ids}) OR seller_id IN ({ids})"
        c.execute(f"DELETE FROM user_ratings WHERE conversation_id IN ({conversations})")
        c.execute(f"DELETE FROM messages WHERE conversation_id IN ({conversations})")
        c.execute(f"DELETE FROM conversations WHERE buyer_id IN ({ids}) OR seller_id IN ({ids})")
        c.execute(f"DELETE lp FROM listing_photos lp JOIN user_listings l ON l.id = lp.listing_id WHERE l.user_id IN ({ids})")
        c.execute(f"DELETE FROM user_listings WHERE user_id IN ({ids})")
        c.execute(f"DELETE FROM user_favorites WHERE user_id IN ({ids})")
        c.execute(f"DELETE FROM users WHERE id IN ({ids})")
    for key in keys:
        storage.delete(key)
    log.info("Demo marketplace removed: %d users, %d photo files", len(users), len(keys))


def photo(title, platform, n, colour):
    """A generated "photo" of the game: a box with its name on a coloured table, marked DEMO."""
    image = Image.new("RGB", (1600, 1200), colour)
    draw = ImageDraw.Draw(image)
    for y in range(0, 1200, 8):                      # a little texture, so it doesn't look flat
        shade = tuple(max(0, v - (y % 40) // 4) for v in colour)
        draw.line([(0, y), (1600, y)], fill=shade, width=4)
    angle = (-6, 3, 8)[n % 3]
    box = Image.new("RGB", (700, 900), (245, 245, 245))
    box_draw = ImageDraw.Draw(box)
    box_draw.rectangle([0, 0, 699, 110], fill=(20, 60, 160))
    box_draw.text((30, 30), platform, fill="white", font=ImageFont.load_default(size=48))
    words, lines = title.split(), [""]
    for word in words:                               # wrap the title on the box
        if len(lines[-1]) + len(word) > 16:
            lines.append("")
        lines[-1] = f"{lines[-1]} {word}".strip()
    for i, line in enumerate(lines[:5]):
        box_draw.text((40, 200 + i * 80), line, fill=(30, 30, 30), font=ImageFont.load_default(size=56))
    box = box.rotate(angle, expand=True, fillcolor=colour)
    image.paste(box, ((1600 - box.width) // 2, (1200 - box.height) // 2))
    draw.text((40, 1110), f"DEMO · foto {n + 1}", fill="white", font=ImageFont.load_default(size=44))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85)
    return out.getvalue()


def add():
    remove()
    rng = random.Random(10794)       # the same demo every time
    users = {}
    for username, name in USERS:
        users[username] = auth_service.register(username, f"{username}@demo.invalid", DEMO_PASSWORD, name)["id"]

    # Popular games in stock: the editions with the most stores, each with its best store price
    games = fetch_all(f"""
        SELECT TOP ({GAMES}) g.id AS game_id, e.id AS edition_id, g.title, p.name AS platform, MIN(o.price) AS price
        FROM current_offers o
        JOIN games g ON g.id = o.game_id JOIN platforms p ON p.id = g.platform_id
        JOIN game_editions e ON e.id = o.edition_id
        WHERE o.is_active = 1 AND o.in_stock = 1 AND o.condition = 'new' AND e.edition_key = ''
        GROUP BY g.id, e.id, g.title, p.name
        HAVING COUNT(DISTINCT o.store_id) >= 3 AND MIN(o.price) >= 15
        ORDER BY COUNT(DISTINCT o.store_id) DESC, MAX(o.price) DESC
    """)
    sellers = list(users)
    listings = []
    for i in range(LISTINGS):
        g = games[i % len(games)]
        seller = sellers[i % len(sellers)]          # a game's second listing has another seller
        condition = rng.choice(list(CONDITION_SHARE))
        price = round(g["price"] * CONDITION_SHARE[condition] / 0.5) * 0.5 - 0.01
        colour = rng.choice([(120, 85, 60), (60, 70, 90), (90, 110, 80), (140, 130, 120)])
        photos = [photo(g["title"], g["platform"], n, colour) for n in range(3 + i % 3)]
        listing = listing_service.create_listing(users[seller], g["game_id"], g["edition_id"], max(price, 4.99),
                                                 condition, rng.choice(DESCRIPTIONS), photos)
        listings.append((listing, seller))
    log.info("%d demo listings", len(listings))

    # Conversations at every purchase step (buyer, steps taken, messages)
    def buyer_for(seller, k):
        return [u for u in sellers if u != seller][k % (len(sellers) - 1)]

    stories = [
        ([], ["Olá! Ainda está disponível?", "Sim, está!"]),
        (["request"], ["Quero comprar, pode ser por MB Way?"]),
        (["request", "accept"], ["Combinado, envio amanhã.", "Obrigado!"]),
        (["request", "accept", "sent"], ["Já enviei, aqui vai o código CTT: RR123456789PT"]),
        (["request", "accept", "sent", "received"], ["Chegou em perfeito estado, obrigado!"]),
        (["request", "accept", "sent", "problem"], ["O disco chegou com um risco que não estava nas fotos."]),
        (["request", "decline"], ["Desculpe, já tinha prometido a outra pessoa."]),
    ]
    sellers_role = {"accept", "decline", "sent"}
    for k, (steps, lines) in enumerate(stories):
        listing, seller = listings[k]
        buyer = buyer_for(seller, k)
        conversation_id = chat_service.start(users[buyer], listing["id"], message=lines[0])
        for action in steps:
            chat_service.deal_step(users[seller if action in sellers_role else buyer], conversation_id, action)
        for j, line in enumerate(lines[1:]):
            chat_service.send_message(users[seller if j % 2 == 0 else buyer], conversation_id, line)

    # Spread the dates over the last weeks, so "published" / message times look real
    with connection() as conn:
        c = conn.cursor()
        demo_ids = ",".join(str(i) for i in users.values())
        c.execute(f"UPDATE users SET created_at = DATEADD(DAY, -(30 + id % 200), created_at) WHERE id IN ({demo_ids})")
        c.execute(f"UPDATE user_listings SET created_at = DATEADD(HOUR, -(id % 300), created_at) WHERE user_id IN ({demo_ids})")
    log.info("Demo conversations: %d. Log in as e.g. demo_ana / %s", len(stories), DEMO_PASSWORD)


if __name__ == "__main__":
    from scheduler.jobs import setup_logging

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--remove", action="store_true", help="remove the demo marketplace")
    args = parser.parse_args()
    setup_logging()
    remove() if args.remove else add()
