---
status: accepted
---

# Changes need our request header and a SameSite cookie; scripts run only from files

The login is a signed session cookie, HttpOnly and SameSite=Lax. Every request that changes something (POST, PUT, PATCH, DELETE) must carry `X-Requested-With: fetch`, or `app/web.py` answers 403 (since 2026-10-02). Another site's page can't add that header to a request to us, because the site sends no CORS headers. There are no CSRF tokens: the pages talk to the API through `api()` in `static/common.js`, which adds the header, so nothing else has to be carried in a page.

The Content-Security-Policy runs scripts only from our own files and the pinned CDN, so an injected `<script>` or `onclick` is refused (since 2026-10-05). Page scripts live in `static/pages/`.

## Consequences

- Every change a page makes goes through `api()`. A plain HTML form that posts to the site is refused.
- Inline scripts and inline event handlers don't run. `tests/test_csp.py` checks that the pages have none.
