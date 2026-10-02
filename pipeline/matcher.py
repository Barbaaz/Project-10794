from core.editions import parse_title, learn_phrase


class GameMatcher:
    """
    Links a scraped product to a game and one of its editions, creating them if needed.
    Two products are the same game when the base title (without edition) and platform match,
    and the same edition when the edition key also matches.
    """

    def __init__(self, cursor, platform_ids):
        self.cursor = cursor
        self.platform_ids = platform_ids   # {"PS5": 1, ...}
        self.games = {}                    # {(game_key, platform_id): game_id}
        self.editions = {}                 # {(game_id, edition_key): edition_id}

        # Edition phrases from stores that write "Title - X Edition", to split
        # names from stores that don't ("TITLE X EDITION")
        names = cursor.execute("SELECT external_name FROM store_products WHERE external_name LIKE '% - %'").fetchall()
        self.known_phrases = set()
        self.learn(row[0] for row in names)

    def learn(self, names):
        for name in names:
            phrase = learn_phrase(name)
            if phrase:
                self.known_phrases.add(phrase)

    def match(self, product):
        """(game_id, edition_id), or (None, None) when the platform is unknown."""
        platform_id = self.platform_ids.get(product["console"])
        parsed = parse_title(product["external_name"], self.known_phrases)

        if not platform_id or not parsed.game_key:
            return None, None

        game_id = self.games.get((parsed.game_key, platform_id))
        if game_id is None:
            game_id = self.get_or_create_game(parsed, platform_id, product.get("image"))
            self.games[(parsed.game_key, platform_id)] = game_id

        edition_id = self.editions.get((game_id, parsed.edition_key))
        if edition_id is None:
            edition_id = self.get_or_create_edition(game_id, parsed)
            self.editions[(game_id, parsed.edition_key)] = edition_id

        return game_id, edition_id

    def get_or_create_game(self, parsed, platform_id, image):
        row = self.cursor.execute(
            "SELECT id, title FROM games WHERE normalized_title = ? AND platform_id = ?",
            parsed.game_key, platform_id,
        ).fetchone()

        if row:
            game_id, title = row
            # Prefer "Silent Hill: Townfall" over Mega Mania's "SILENT HILL TOWNFALL"
            if title.isupper() and not parsed.game_title.isupper():
                self.cursor.execute("UPDATE games SET title = ? WHERE id = ?", parsed.game_title[:300], game_id)
            return game_id

        return self.cursor.execute(
            """
            INSERT INTO games (platform_id, title, normalized_title, image_url)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?)
            """,
            platform_id, parsed.game_title[:300], parsed.game_key, image,
        ).fetchone()[0]

    def get_or_create_edition(self, game_id, parsed):
        row = self.cursor.execute(
            "SELECT id FROM game_editions WHERE game_id = ? AND edition_key = ?",
            game_id, parsed.edition_key,
        ).fetchone()

        if row:
            return row[0]

        return self.cursor.execute(
            """
            INSERT INTO game_editions (game_id, edition_key, name)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?)
            """,
            game_id, parsed.edition_key, parsed.edition_name[:200],
        ).fetchone()[0]
