---
status: proposed
---

# Price per hour: the edition's best price over IGDB's story time, worked out in the page

Beside each edition's best price, the game page shows what an hour of the main story costs: "24,99 € · about 1 € per hour of story". We decided to:

- **Use the story time**, `ttb_hastily`, which the page already labels "História". It's the shortest of IGDB's three times, so the figure never makes a game look cheaper per hour than it is for someone who only plays the story.
- **Use the edition's best price now**: new, in stock, at any store (`best_price` on each edition in the game payload). With no copy in stock, there's no figure.
- **Show it only with enough players**: IGDB times from at least 5 players (`ttb_count`). This is a starting value.
- **Work it out in the page script** from fields the game payload already carries (`ttb_hastily`, `ttb_count`, each edition's `best_price`). No new query, column or API field.
- **Show a number, never a judgement.** There's no "good value" label: a fair price per hour differs between a 6-hour indie and a 100-hour role-playing game.

## Considered options

- **The 100% time** (`ttb_completely`). Rejected: most players never finish everything, so it would make games look cheaper per hour than they are for most buyers.
- **The "Com extras" time** (`ttb_normally`). A fair middle ground. Story time won because it's the most conservative.
- **Sorting the catalogue by price per hour.** Not now: it needs the figure in SQL for every edition. Revisit if people ask for it.

## Consequences

- Deluxe and Collector's editions cost more per hour, since IGDB's time is for the game and not its extras.
- Consoles, and games IGDB has no times for, show nothing. Unreleased games rarely have player times, so their figure stays hidden too.
- Two new texts in `static/i18n.js`, in both languages.
