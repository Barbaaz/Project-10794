---
status: accepted
---

# Scrapers stay polite, and a store that refuses us is left alone

Every request to a store goes through `scrapers/base/http_client.py`:

- one request at a time, at least 3 seconds (plus up to 2 random) apart, or longer when the store's robots.txt asks for a longer Crawl-delay;
- never a URL robots.txt disallows, wildcard rules included;
- at most 600 requests per store per run, and no new run within 8 hours of a successful one;
- a 403 or 429 ends that store's run, and the store is left alone for 24 hours.

We don't work around a refusal. A store that keeps refusing is switched off, as Darty was on 2026-10-03.

Requests carry a browser's User-Agent. From 2026-10-07 to 2026-10-08 they said "Project10794-bot/1.0", and CSTech answered 429 to every one while its site still opened in a browser. The user chose to go back to the browser User-Agent for every store (2026-10-08).

## Considered options

- **A bot User-Agent**, the usual courtesy that lets a store see who is asking. Dropped after CSTech refused every request.
- **Retrying past a 403 or 429.** Rejected: a refusal ends the run.
- **Stores behind a captcha or a Cloudflare challenge** (Fnac, Worten, shop4nerds) **or whose terms forbid scraping** (Amazon) were not added (2026-10-02 and 03).

## Consequences

- A store can't tell our requests from a visitor's, so robots.txt, the gaps between requests and stopping at a refusal are what keep the scraping polite. Changes to the HTTP client keep all three.
- Prices are at most about 12 hours old for the stores in the light run, and about a day old for the others.
