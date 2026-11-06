---
status: proposed
---

# The sell form suggests a range from used prices, never a single price

Today the sell form shows only the best new price at a store (`storePriceHint` in `static/pages/sell.js`). We decided to add a range for a used copy of the same edition:

- **Two sources, each with its count**: used copies stores sell now (store offers with condition `used`, in stock, such as Gaming Replay's "Seminovos"), and marketplace listings of that edition sold in the last 180 days (status `sold`, by `sold_at`; see `app/services/listing_service.py`). The text gives each count: "4 used copies in stores, 3 sales here".
- **The range** runs from the lowest of those prices to their median.
- **A privacy floor**: marketplace sales count only when there are at least 3 for the edition, so no one's single sale price can be read from the hint. Listings a moderator removed never count.
- **Advice only**: the hint never fills in the price field. The best new price stays beside it as the ceiling it already is.
- **Worked out on read** by a small endpoint for one edition, kept 10 minutes with `cached`.

## Considered options

- **One suggested price.** Rejected: with few data points it's false precision, and copies differ (box, manual, condition).
- **Listings still for sale.** Rejected: those are asking prices, not prices paid.
- **Falling back to the game's other editions.** Rejected: editions differ in value, which is why they're separate.

## Consequences

- The price paid is taken as the listing's price when it sold: the purchase steps carry no price of their own.
- Early on, with few sales, the range comes mostly from stores' used copies. With neither source, the form shows only the new price, as it does today.
