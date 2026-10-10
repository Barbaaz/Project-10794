"""
Games that may be the same one written differently by two stores, for the moderators' list of
possible duplicates (app/services/match_service.py): "KINGDOM HEARTS I-III" / "Kingdom Hearts
Collection I-III", "Zelda Breath of the Wild" / "The Legend of Zelda: Breath of the Wild",
"Dinasty Warriors 9 Empires" / "DYNASTY WARRIORS 9 EMPIRES". Suggestions only: never merged
automatically (a wrong merge is worse than a duplicate).

Rules, on the matching keys (core/normalizer.py):
- the same platform, and the same numbers and single letters ("Taxi Chaos" / "Taxi Chaos 2",
  "Xenoblade Chronicles" / "Xenoblade Chronicles X" are two games);
- most words the same (a long word may differ by a typo), or one name wholly inside the other;
- not a bundle against one of its games ("Odyssey + Valhalla" / "Odyssey"), nor an expansion or
  a spin-off ("The Sims 4 Expansão Get Famous", "F1 Manager 23" / "F1 23");
- not two games IGDB matched to different entries (IGDB already tells them apart).
"""
import re
from collections import defaultdict
from difflib import SequenceMatcher

from core.normalizer import numerals

MIN_SHARE = 0.75          # words matched / words of the longer name
TYPO_RATIO = 0.85         # two long words this alike are the same word misspelt
MIN_TYPO_LENGTH = 5
# words too common to bring two names together on their own
COMMON = {"the", "of", "and", "a", "edition", "game", "collection", "deluxe", "remastered", "hd"}
# a word only one of the two names has that makes it another product
OTHER_PRODUCT = {"manager", "kids", "online", "expansao", "expansion", "dlc", "season", "bundle", "pack", "double",
                 "compilation", "trilogy", "twin", "duplo", "jogos", "games", "micros", "microfones", "abba", "pets",
                 "tycoon", "party", "racing", "golf", "tennis", "football", "basketball"}
# a title joining games: "Odyssey + Valhalla", "Child of Light & Valiant Hearts", "Memories / Later x Crowd"
ROMAN = re.compile(r"[ivxlc]+")
JOINED = re.compile(r"\s[+&/]\s|\s\+|\+\s")


def _same_word(a, b):
    return a == b or (len(a) >= MIN_TYPO_LENGTH and len(b) >= MIN_TYPO_LENGTH
                      and SequenceMatcher(None, a, b).ratio() >= TYPO_RATIO)


def similar(key_a, key_b, title_a="", title_b=""):
    """Whether two games may be the same (see the rules above): their matching keys, and their
    titles when known (a "+" between games is gone from the keys)."""
    a, b = numerals(key_a).split(), numerals(key_b).split()
    if not a or not b or a == b:
        return False
    # numbers, single letters and Roman numerals ("I-III" is the word "iiii" in old keys) must agree
    exact = lambda words: sorted(w for w in words if w.isdigit() or len(w) == 1 or ROMAN.fullmatch(w))
    if exact(a) != exact(b):
        return False
    if (set(a) ^ set(b)) & OTHER_PRODUCT:
        return False
    if bool(JOINED.search(title_a)) != bool(JOINED.search(title_b)):
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    unmatched = list(longer)
    matched = 0
    for word in shorter:
        hit = next((w for w in unmatched if _same_word(word, w)), None)
        if hit is not None:
            unmatched.remove(hit)
            matched += 1
    if matched == len(shorter) and len([w for w in shorter if w not in COMMON]) >= 2:
        return True                       # one name wholly inside the other
    # the share counts the words that tell games apart ("Tales of Berseria / Symphonia Remastered": 1 of 2)
    # (numbers already agree: they don't count again)
    telling = lambda w: w not in COMMON and not w.isdigit() and len(w) > 1 and not ROMAN.fullmatch(w)
    significant = [w for w in longer if telling(w)]
    matched_significant = len(significant) - len([w for w in unmatched if telling(w)])
    return bool(significant) and matched_significant / len(significant) >= MIN_SHARE


def similar_pairs(games):
    """
    games: [(id, platform_id, key, igdb_id, title)]. The pairs (smaller id, larger id) that may be
    the same game. Candidates share an uncommon word, so not every pair of games is compared.
    """
    by_word = defaultdict(set)
    info = {}
    for game_id, platform_id, key, igdb_id, title in games:
        info[game_id] = (platform_id, key, igdb_id, title)
        for word in set(numerals(key).split()) - COMMON:
            if not word.isdigit():
                by_word[(platform_id, word)].add(game_id)
    pairs = set()
    for ids in by_word.values():
        if len(ids) > 200:                # a word half the catalogue has ("star", "world") brings nothing
            continue
        for a in ids:
            for b in ids:
                if a < b and (a, b) not in pairs:
                    pa, pb = info[a], info[b]
                    if pa[2] and pb[2] and pa[2] != pb[2]:
                        continue
                    if similar(pa[1], pb[1], pa[3], pb[3]):
                        pairs.add((a, b))
    return sorted(pairs)
