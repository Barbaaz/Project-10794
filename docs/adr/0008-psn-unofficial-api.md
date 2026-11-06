---
status: accepted
---

# The PSN import uses PSN's unofficial API

Importing a user's PlayStation games and trophies (since 2026-10-12) goes through the API the PlayStation app uses. Sony offers no public one, and its terms don't allow this use. The user accepted that risk, including the chance that the site's PSN account gets blocked. The site signs in with one PSN account's NPSSO token (`PSN_NPSSO`, never in the code). The token lasts about two months; then an admin saves a new one.

## Considered options

- **No PSN import.** PlayStation players would add their games by hand, while Steam players import theirs through Steam's public Web API.

## Consequences

- The import can stop without warning if Sony changes the API or blocks the account. Everything PSN-specific is in `app/services/psn_service.py`.
- An expired token shows in the log as "PSN refused the NPSSO token".
