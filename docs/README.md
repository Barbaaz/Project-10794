# Knowledge base

Why SaveOnGames is built the way it is, the words it uses, how its parts fit, and how to do things in it. What each module does is in its own docstring; these pages hold the rest.

## Start here

- **[Architecture](architecture.md)**: the whole system on one page. Read it before your first change to a part you don't know.
- **[Glossary](../GLOSSARY.md)**: the project's terms, and the words to avoid. Read it before naming anything.

## Decisions

One file per decision in [adr/](adr/). Read the ones that touch the area you're changing before you change how it works.

| ADR | Decision | Status |
|---|---|---|
| [0001](adr/0001-buy-or-wait-verdict.md) | The buy-or-wait verdict, told from past real discounts | Proposed |
| [0002](adr/0002-postgresql-two-schemas.md) | PostgreSQL, with the price side in SQL scripts and the marketplace in Alembic | Accepted |
| [0003](adr/0003-real-discounts.md) | A discount is real only against our own 30-day price history | Accepted |
| [0004](adr/0004-polite-scraping.md) | Scrapers stay polite, and a store that refuses us is left alone | Accepted |
| [0005](adr/0005-web-app-never-calls-stores.md) | The web app never contacts the stores | Accepted |
| [0006](adr/0006-half-broken-scraper-safeguard.md) | A run with under 70% of the last run's products deactivates nothing | Accepted |
| [0007](adr/0007-request-guards.md) | Changes need our request header and a SameSite cookie; scripts run only from files | Accepted |
| [0008](adr/0008-psn-unofficial-api.md) | The PSN import uses PSN's unofficial API | Accepted |
| [0009](adr/0009-who-creates-games.md) | Only stores and IGDB create games; never a typed name | Accepted |
| [0010](adr/0010-price-per-hour.md) | Price per hour: the edition's best price over IGDB's story time, worked out in the page | Proposed |
| [0011](adr/0011-store-pages.md) | Store pages show measured facts about each store, never a score | Proposed |
| [0012](adr/0012-weekly-deals-digest.md) | A weekly deals digest by platform: opt-in, separate from wishlist alerts | Proposed |
| [0013](adr/0013-deal-feeds.md) | Deal feeds: one Atom feed of real discounts, filtered by platform | Proposed |
| [0014](adr/0014-sell-price-hint.md) | The sell form suggests a range from used prices, never a single price | Proposed |
| [0015](adr/0015-collection-value-over-time.md) | Collection value over time: monthly, from store price history, for the games owned then | Proposed |

## How-to

- **[When a store's run fails or warns](how-to/store-run-problems.md)**: blocked, no products, or too few.
- **[Fix a wrong match](how-to/fix-a-wrong-match.md)**: one offer, two games that are one, or a matching rule.
- **[Change a table](how-to/change-a-table.md)**: on the price side or the marketplace side.
- **Covered in README.md and DEPLOY.md**: [add a store](../README.md#adding-a-store), [load demo data](../README.md#try-it-with-docker), [run the tests](../README.md#tests), [make someone a moderator or admin](../DEPLOY.md#looking-after-it), [update the server](../DEPLOY.md#updating-to-newer-code), [restore a backup](../DEPLOY.md#backups).

## Running and deploying

- **[README.md](../README.md)**: setup with Docker or on Windows, the API, tests, adding a store.
- **[DEPLOY.md](../DEPLOY.md)**: the server, updates and backups.

## Rules for agents

- **[agents/](agents/)**: Python and frontend rules, the issue tracker and its labels. [AGENTS.md](../AGENTS.md) says when to read each.

## Adding to it

- **Write** the why, the how-to steps and the terms. What the code does belongs in the code's docstrings.
- **A decision** that affects one place stays as a `(user, YYYY-MM-DD)` comment beside the code. One that spans modules, or that someone might undo without knowing why, becomes an ADR: the next number in `docs/adr/`, as `NNNN-short-title.md`.
- **A how-to** covers one task in `docs/how-to/`: the steps, then how to tell it worked. A task README.md or DEPLOY.md already covers gets a link here instead.
- **A new term** goes in the glossary, with the words to avoid.
- **This index** lists every ADR and how-to; add yours here.
- **Paths**: `tests/test_docs.py` fails when a page here names a file or folder that doesn't exist.
