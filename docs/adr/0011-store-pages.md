---
status: proposed
---

# Store pages show measured facts about each store, never a score

Each active store gets a page, `/store/<slug>`, with what our own data says about it. We decided to:

- **Show facts, not a rating**:
  - how often its offers had a real discount in the last 90 days ([ADR 0003](0003-real-discounts.md));
  - how often it's the cheapest store for the editions it sells;
  - how fresh its prices are: last successful run, last status and the 36-hour stale flag, as `/api/stores` already reports them (`app/routes/stores.py`);
  - its best real discounts now.
- **Say what each figure counts**: "of the N offers we follow at this store".
- **Work it out on read** for one store, kept 10 minutes with `cached`, from `current_offers` and the price history. Nothing is stored.
- **Link to it** from the store's name in the buy box and in the footer's store status.
- **Active stores only**, the same ones `/api/stores` lists.

## Considered options

- **An overall score or a ranking of stores.** Rejected: we read some catalogues only in part. Techinn's category pages show only its most popular games, and Rádio Popular's offers count only when they match a known game ([ADR 0009](0009-who-creates-games.md)). A single score would mostly measure our coverage, and would be unfair to those stores.
- **Storing per-store figures after the daily run.** Rejected for now, for the reasons in [ADR 0001](0001-buy-or-wait-verdict.md).

## Consequences

- The page states which part of the catalogue we follow for stores read in part.
- The page's text about stores stays factual. Nothing on it calls a store reliable or unreliable.
- A store switched off (`is_active` false) has no page.
