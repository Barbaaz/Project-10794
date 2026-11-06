---
status: proposed
---

# Collection value over time: monthly, from store price history, for the games owned then

/collection gets a chart of what the user's games were worth at the end of each of the last 12 months, plus today. We decided to:

- **Count the games owned then**: the owned items whose `created_at` is on or before each month's end. The chart shows prices moving and the collection growing.
- **Value them at the best new price** in stock at any store on that date, read from the price history. This is the same basis as today's `worth_new` in `app/services/collection_service.py`.
- **Leave used value out of the chart**: listings keep only their latest price, with no history, so used value exists for today only.
- **Say how many were priced**: an edition with no price on a date doesn't count that month, and the chart shows how many games were priced, like `priced_new` does today.
- **Work it out on read** for one user, kept 10 minutes with `cached`. A public collection shows the chart under the same rules as the rest of it.

## Considered options

- **Storing a snapshot of each collection every month.** Rejected: the price history already holds everything needed to rebuild it, so no new table.
- **Valuing today's collection backwards**, ignoring when games were added. It answers a different question ("what would these games have cost then"). It could become a toggle later.

## Consequences

- Imported games carry the import date, so an import shows as a jump in that month.
- Games taken out of the collection disappear from earlier months too, because the chart reads the current items only.
- History starts with the scraping (spring 2026), so earlier months show nothing.
- Collections have no size limit (user, 2026-10-15). The query must find each edition's best price at each month's end in one pass, and it needs a test with thousands of items.
