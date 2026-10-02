from difflib import SequenceMatcher

from core.close_match import KeyIndex
from core.editions import EDITION_WORDS, parse_title, learn_phrase, edition_key_of, cut_display

MIN_TYPO_LENGTH = 5     # words this long may differ by a typo ("delixe" / "deluxe")
TYPO_SIMILARITY = 0.8
NOT_TITLE_WORDS = EDITION_WORDS | {"ultra", "anniversary", "th"}   # never moved from an edition into a title


class GameMatcher:
    """
    Links a scraped product to a game and one of its editions, creating them if needed.
    Two products are the same game when the base title (without edition) and platform match,
    and the same edition when the edition key also matches. On top of the exact keys:
    - a shortened name goes to the one fuller known game it fits ("doom dark ages" →
      "doom the dark ages", core/close_match.py);
    - a name cut in the wrong place is mended: "Star Wars" + edition "Galactic Racer Deluxe"
      → "Star Wars Galactic Racer" + "Deluxe" when that game is known;
    - an edition differing by a typo from one the game has is that edition ("delixe" → "deluxe").
    """

    def __init__(self, cursor, platform_ids):
        self.cursor = cursor
        self.platform_ids = platform_ids   # {"PS5": 1, ...}
        self.games = {}                    # {(game_key, platform_id): game_id}
        self.editions = {}                 # {(game_id, edition_key): edition_id}
        self.game_editions = {}            # {game_id: {edition_key: edition_id}}, loaded per game

        # Edition phrases from stores that write "Title - X Edition", to split
        # names from stores that don't ("TITLE X EDITION")
        names = cursor.execute("SELECT external_name FROM store_products WHERE external_name LIKE '% - %'").fetchall()
        self.known_phrases = set()
        self.learn(row[0] for row in names)

        # Known game keys per platform, for the fuller-name and mended-title rules
        self.keys = {}
        for key, platform_id in cursor.execute("SELECT normalized_title, platform_id FROM games").fetchall():
            self.keys.setdefault(platform_id, KeyIndex()).add(key)

    def learn(self, names):
        for name in names:
            phrase = learn_phrase(name)
            if phrase:
                self.known_phrases.add(phrase)

    def match(self, product):
        """(game_id, edition_id), or (None, None) when the platform is unknown."""
        return self.match_details(product)[:2]

    def match_details(self, product):
        """
        (game_id, edition_id, game_title, edition_name). game_title is None when the name was
        shortened or cut wrongly: it isn't a good display title for the game it went to.
        """
        platform_id = self.platform_ids.get(product["console"])
        parsed = parse_title(product["external_name"], self.known_phrases)

        if not platform_id or not parsed.game_key:
            return None, None, None, None

        index = self.keys.setdefault(platform_id, KeyIndex())
        game_key, edition_key, edition_name = self.mend_split(parsed, index)
        game_key = index.resolve(game_key)
        own_title = parsed.game_title if game_key == parsed.game_key else None

        game_id = self.games.get((game_key, platform_id))
        if game_id is None:
            game_id = self.get_or_create_game(game_key, own_title, platform_id, product.get("image"))
            self.games[(game_key, platform_id)] = game_id
            index.add(game_key)

        edition_id = self.editions.get((game_id, edition_key))
        if edition_id is None:
            edition_id = self.get_or_create_edition(game_id, edition_key, edition_name)
            self.editions[(game_id, edition_key)] = edition_id

        return game_id, edition_id, own_title, edition_name

    def mend_split(self, parsed, index):
        """
        (game_key, edition_key, edition_name). When the edition starts with words that belong to
        the title ("Star Wars" + "Galactic Racer Deluxe"), and title + those words is a known
        game, the words move to the title.
        """
        words = parsed.phrase.split()
        tags = parsed.edition_key.split("|")[1:]
        for n in range(len(words), 0, -1):
            # Edition words don't move: "Dead Island" + "Definitive Edition" must not go to a
            # "Dead Island Definitive" game (a store that wrote the edition into the title)
            if set(words[:n]) & NOT_TITLE_WORDS:
                continue
            longer = f"{parsed.game_key} {' '.join(words[:n])}"
            if longer in index:
                key = edition_key_of(" ".join(words[n:]))
                _, rest = cut_display(parsed.edition_name, n)
                rest = rest.strip(" ·")
                name = rest if key else " · ".join(["Standard"] + tags)
                return longer, "|".join([key] + tags), name or "Standard"
        return parsed.game_key, parsed.edition_key, parsed.edition_name

    def get_or_create_game(self, game_key, title, platform_id, image):
        row = self.cursor.execute(
            "SELECT id, title FROM games WHERE normalized_title = ? AND platform_id = ?",
            game_key, platform_id,
        ).fetchone()

        if row:
            game_id, current = row
            # Prefer "Silent Hill: Townfall" over Mega Mania's "SILENT HILL TOWNFALL"
            # (title is None for a shortened or mended name: not this game's own title)
            if title and current.isupper() and not title.isupper():
                self.cursor.execute("UPDATE games SET title = ? WHERE id = ?", title[:300], game_id)
            return game_id

        # A new game comes from its own name (resolve() and mend_split() only go to known games)
        return self.cursor.execute(
            """
            INSERT INTO games (platform_id, title, normalized_title, image_url)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?)
            """,
            platform_id, (title or game_key)[:300], game_key, image,
        ).fetchone()[0]

    def get_or_create_edition(self, game_id, edition_key, name):
        known = self.game_editions.get(game_id)
        if known is None:
            known = dict(self.cursor.execute(
                "SELECT edition_key, id FROM game_editions WHERE game_id = ?", game_id).fetchall())
            self.game_editions[game_id] = known

        if edition_key in known:
            return known[edition_key]
        typo = next((key for key in known if same_with_typos(edition_key, key)), None)
        if typo is not None:
            return known[typo]

        edition_id = self.cursor.execute(
            """
            INSERT INTO game_editions (game_id, edition_key, name)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?)
            """,
            game_id, edition_key, name[:200],
        ).fetchone()[0]
        known[edition_key] = edition_id
        return edition_id


def same_with_typos(a, b):
    """
    Two edition keys of the same game that differ only by typos: same tags, same number of
    words, and each word the same or (5+ letters) nearly the same ("steeelbook" / "steelbook",
    "enrolment" / "enrollment"). Numbers must be the same.
    """
    (a_words, *a_tags), (b_words, *b_tags) = a.split("|"), b.split("|")
    a_words, b_words = a_words.split(), b_words.split()
    if a_tags != b_tags or len(a_words) != len(b_words) or not a_words or a_words == b_words:
        return False
    for x, y in zip(a_words, b_words):
        if x == y:
            continue
        if min(len(x), len(y)) < MIN_TYPO_LENGTH or x.isdigit() or y.isdigit():
            return False
        if SequenceMatcher(None, x, y).ratio() < TYPO_SIMILARITY:
            return False
    return True
