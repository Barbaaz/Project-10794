# Fix a wrong match

Three cases, from one offer up to the rules themselves. The first two are done on the site as a moderator, in /admin.

## One offer is on the wrong game or edition

1. In /admin, open the **Correspondências** tab and find the store's product.
2. Move it to the right edition, to another game, or to a new edition. The move pins it: the daily run and later rematches leave it there. A game or edition the move leaves empty is merged into where its products went.

**It worked when** the game page shows the offer under the right edition. To let the rules decide again, unpin the product; the next rematch places it.

## Two games are one game

The **Possíveis duplicados** list in /admin shows games that may be one game written differently by two stores. Merge the pair, or dismiss it so it isn't suggested again.

**It worked when** the game's old page sends you to the one kept, and its listings, collection items and reviews show there.

## Many offers go wrong the same way

The rules are wrong, not the offer.

1. Change the rule in `core/`: `editions.py` splits a store's name into game and edition, `normalizer.py` cleans names, `close_match.py` matches shortened names, and `titles.py` picks the spelling shown.
2. Add the failing name as a case in `tests/test_editions.py`, `tests/test_close_match.py` or `tests/test_titles.py`, and make it pass.
3. See what the new rules would change, without changing anything: `python -m pipeline.rematch --dry-run`. Read the merges it lists.
4. Apply them: `python -m pipeline.rematch`.

**It worked when** the dry run lists only the merges you expected, and the games look right on the site afterwards. Pinned products are left where moderators put them.
