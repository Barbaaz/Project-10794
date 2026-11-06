---
status: accepted
---

# The web app never contacts the stores

Pages and the API read prices only from the database. The daily run is the only code that requests a store's pages (`app/web.py`: "Nothing here scrapes the stores"). A visit never waits on a store, and the requests a store gets don't grow with the number of visitors, which keeps the limits of [ADR 0004](0004-polite-scraping.md) meaningful.

## Considered options

- **Checking a store live when a game page opens.** Rejected: every visit would add requests to the stores, could set off their 429s, and would make a page as slow as the slowest store.

## Consequences

- A price is as old as the last run of its store. The footer shows ⚠ beside a store that failed, looked half-broken or hasn't updated for 36 hours.
- The web app still calls other outside services: IGDB for games no store sells, Steam and PSN for imports, SMTP and Web Push. Those aren't stores.
