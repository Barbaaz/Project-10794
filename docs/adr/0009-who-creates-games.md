---
status: accepted
---

# Only stores and IGDB create games; never a typed name

A game exists because a store sells it or because IGDB lists it.

- **Stores**: the daily run creates a game and edition when an offer matches none, except at a match-only store. Rádio Popular is one: its names are cut too short to start games from (its first run made 340 games like "INSP GADGET MAD TIME P"), so its offers only join games that already exist (`MATCH_ONLY_STORES` in `pipeline/matcher.py`).
- **IGDB**: when someone wants to sell or add a game no store sells, the sell form and the collection search IGDB. Picking a result creates the game on that platform, with its IGDB information and a Standard edition (since 2026-10-07; `app/services/igdb_game_service.py`).

Nobody can create a game by typing its name.

## Consequences

- Every game is tied to a store's offer or an IGDB record. If a store later sells a game created from IGDB, the daily run finds it by name.
- A game created from IGDB that nobody uses is removed by the next rematch.
- A Rádio Popular offer that matches no known game stays unlinked and isn't shown.
