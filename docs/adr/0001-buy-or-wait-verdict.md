---
status: proposed
---

# Buy-or-wait verdict: told from past real discounts, worked out when the game page is read

The game page's buy box gets one line per edition saying whether now is a good time to buy: "Good price now", "Usually drops" or "Rarely on sale", with the facts behind it ("On sale 4 times in the last 6 months, down to 39,99 €; the last sale ended 40 days ago"). We decided to:

- **Count real discounts only.** A sale is a price period that `current_offers` would call a discount: lower than the lowest price in the 30 days before it began, on a product watched for those 30 days. The store's crossed-out price is not used.
- **Judge the edition, not the store product**: its new copies that were in stock, across every store, as the historical low already does (`app/services/common.py`, `lowest_prices`).
- **Describe the past, never forecast.** The verdict comes from fixed thresholds over the last 180 days, and its text says what happened, not what will happen. It stays hidden until the edition has been watched for 90 days.
- **Work it out on read**, in SQL, for the editions of the one game being shown, kept for 10 minutes with `cached`. Nothing is stored.
- **Write the price-period rule once.** The step of `database/views.sql` that turns snapshots into price periods becomes a view of its own, read by both `current_offers` and the verdict, so the "on sale" badge and the verdict can't disagree.

## Considered options

- **The store's crossed-out price as the sale signal.** Rejected: many products show one permanently (`database/views.sql`), so almost every game would "usually drop".
- **A forecast** ("likely to drop within 30 days"). Rejected: the history is a few months long and has gaps, which can't back a promise shown to shoppers.
- **Working it out in Python from `get_price_history`.** Rejected: it would be a second copy of the real-discount rule, which lives in SQL.
- **Storing verdicts after the daily run.** Rejected for now: a new price-side table for a value one page reads, and it goes stale whenever the rule changes. Revisit if the verdict becomes a catalogue filter or sort order, which needs it for every edition at once.
- **One verdict per store product.** Rejected: the buy box offers the edition wherever it's cheapest, so which store had the past sales doesn't matter to the shopper.

## Consequences

- Sale counts are a floor: a sale that starts and ends between two runs leaves no snapshot (on the PC, runs happen only while it's on). Long gaps in a store's `scrape_runs` make "Rarely on sale" less trustworthy.
- Pulling the price periods into their own view changes `current_offers`, which every catalogue page reads. Its speed must be measured again on a realistic database: the 6-second plan noted in `views.sql` (2026-10-04) came from that query.
- The local database has no price snapshots, so tests build their own price histories. Checking the thresholds against real prices needs the server's database or the demo data file.
- The thresholds (within 3% of the 180-day low, at least 2 sales, 180 and 90 days) are starting values, kept as constants in the service and tuned once verdicts can be compared with what prices did next.
