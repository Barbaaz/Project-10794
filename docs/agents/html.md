# Frontend: templates and static files

## Pages

- **A page** is `templates/<page>.html` (a full document that includes `_header.html` and `_footer.html`) plus its script, `static/pages/<page>.js`. Shared scripts: `common.js` (`api`, `esc`, the account area, the theme), `i18n.js` (texts) and `market.js`.
- **Ids**: the header's element ids belong to the header (`tests/test_page_ids.py`), so give page elements ids of their own.
- **Styling**: Bootstrap 5.3 classes first, shared rules in `static/common.css`, and a page's own `<style>` only for rules no other page uses. Colours are CSS custom properties with a value under `[data-bs-theme="dark"]`.

## Scripts and safety

- **Scripts live in files.** Handlers attach with `addEventListener`, using `data-*` attributes to find their elements. The Content-Security-Policy refuses inline `<script>` and `on…="…"` attributes (`tests/test_csp.py`).
- **API calls** go through `api(path, {method, body})` from `common.js`. It adds the `X-Requested-With: fetch` header that `app/web.py` requires on every change, and resolves to `{ok, status, data}`.
- **User and API text** reaches HTML through `esc()` (attribute values included) or `textContent`. Jinja's autoescaping covers template output.
- **CDN files** are pinned to an exact version, with `integrity` and `crossorigin` (`tests/test_cdn_files.py`).

## Text and accessibility

- **Visible text** is a key in `static/i18n.js`, in both `pt` and `en` (`tests/test_i18n.py`). HTML uses `data-i18n`, `data-i18n-placeholder`, `data-i18n-aria-label` and `data-i18n-title`; scripts use `t(key, vars)`.
- **Icon-only buttons** get `type="button"` and a translated `aria-label`, and their SVG gets `aria-hidden="true" focusable="false"`.
