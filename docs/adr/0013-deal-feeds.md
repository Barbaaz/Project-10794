---
status: proposed
---

# Deal feeds: one Atom feed of real discounts, filtered by platform

A public feed of current deals, for feed readers and chat bots, with no account needed. We decided to:

- **Use Atom**, at `/feeds/discounts.atom`, filtered with `?platform=PS5` (the codes `/api/platforms` returns) and `?lang=en` (Portuguese by default, like the site). Atom requires a stable id and an update date on every entry, which is what readers need to avoid repeats.
- **List the discounts tab's items**: real discounts on games, on offers still sold and in stock, from `list_discounts` in `app/services/price_service.py`. The feed takes the 50 biggest, as the tab orders them, and dates each entry by when its price began, so readers sort them by that date. The feed and the tab always agree.
- **Give each entry a stable id**: the offer plus the date its current price began. A reader shows a new entry only when a new discount starts, not after every run.
- **Link to our game page**, where the stores are compared, not to the store's own page.
- **Keep it public and light**: no personal data, GET only, kept 10 minutes with `cached`, sent as `application/atom+xml`.

## Considered options

- **RSS 2.0.** Readers handle both formats; Atom's required id and date fields fit the stable-entry rule better.
- **A documented public JSON API.** Rejected for now: the JSON API serves our own pages and can change with them. A feed is a small, stable contract that readers and bots already understand.
- **Per-user wishlist feeds.** Rejected: they would need a secret token in the address. Wishlist alerts and push already cover that.

## Consequences

- The 10-minute cache absorbs bots that poll often. Add a rate limit only if one shows up in the logs.
- `static/sw.js` must keep feed responses out of what it saves for offline use.
