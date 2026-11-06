---
status: accepted
---

# A discount is real only against our own 30-day price history

The stores' crossed-out prices aren't trusted: many products show one permanently. Like the EU Omnibus rule, a price is a real discount only when it's lower than the lowest price we recorded in the 30 days before it began, on an offer we watched for those whole 30 days. The `current_offers` view in `database/views.sql` decides it (since 2026-10-02). The "on sale" badge, the discounts tab and the catalogue's "on sale" filter read it.

## Considered options

- **The store's crossed-out price.** Rejected: a permanent "was" price would make most games look discounted all the time.

## Consequences

- A new store, or a new offer, can't show a discount for its first 30 days. The daily run has to keep running for discounts to appear.
- The view finds each offer's reference price in one pass of window functions. A join of the price history to itself made every page that reads it slow (6 seconds for 10,000 snapshots, 2026-10-04).
- [ADR 0001](0001-buy-or-wait-verdict.md) counts past sales with this same rule.
