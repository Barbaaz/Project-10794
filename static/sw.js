/*
 * The service worker (served as /sw.js by app/web.py): the site opens on a weak connection or
 * none, and can be installed on a phone's home screen (static/manifest.webmanifest).
 * - pages and our static files: from the network; when it fails or is slow, the copy saved
 *   on the last visit (a page never seen before: static/offline.html)
 * - public API reads (PUBLIC_API): the same, and the page is told it got a saved answer, with
 *   when it was saved (common.js shows it): prices are never shown out of date without saying so
 * - Bootstrap / Chart.js from the CDN: saved once (their URLs name a fixed version)
 * - everything else (the account, messages, collection, moderation, anything that changes
 *   something, other sites' images): straight to the network, never saved here
 * Change VERSION when this file changes what it saves: the old saved copies are dropped.
 */
// v2: CDN files with integrity hashes (v1 may hold opaque copies they can't use)
// v3: page scripts in files (static/pages/); saved pages from before had them inline
// v4: the new look (2026-10-10) and its font
const VERSION = "v4";
const CACHE = `site-${VERSION}`;
const SLOW_MS = 6000;      // past this, a saved copy is shown while the network keeps trying
const CDN = "https://cdn.jsdelivr.net";       // Bootstrap, Chart.js: fixed versions in their URLs
const BOOTSTRAP_CSS = `${CDN}/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css`;

// Saved when the worker is installed, so even the first offline visit has them
const PRECACHE = [
    "/static/offline.html", "/static/pages/offline.js", "/static/common.css", "/static/common.js", "/static/i18n.js",
    "/static/market.js", "/static/fonts/figtree-latin.woff2",
    "/static/favicon.svg", "/static/icons/icon-192.png", BOOTSTRAP_CSS,
];

// API reads that are the same for everyone (no personal data), by path
const PUBLIC_API = [
    /^\/api\/games(\/catalog|\/editions)?$/, /^\/api\/games\/\d+(\/prices)?$/,
    /^\/api\/(discounts|discounts\/featured|deals|preorders|releases|stores|platforms|genres|tags)$/,
    /^\/api\/listings$/,
];

self.addEventListener("install", event => {
    event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
    event.waitUntil(caches.keys()
        .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
        .then(() => self.clients.claim()));
});

self.addEventListener("fetch", event => {
    const request = event.request;
    if (request.method !== "GET") return;
    const url = new URL(request.url);

    if (url.origin === CDN) {
        // a fixed version: the saved copy never goes out of date
        event.respondWith(cacheFirst(request));
    } else if (url.origin !== location.origin) {
        return;
    } else if (request.mode === "navigate") {
        event.respondWith(networkFirst(event, { fallback: "/static/offline.html" }));
    } else if (url.pathname.startsWith("/static/")) {
        event.respondWith(networkFirst(event));
    } else if (PUBLIC_API.some(path => path.test(url.pathname))) {
        event.respondWith(networkFirst(event, { tellPage: true }));
    }
});

// The network's answer (saved for next time); when it fails, or takes longer than SLOW_MS and a
// saved copy exists, the saved copy instead
async function networkFirst(event, { fallback = null, tellPage = false } = {}) {
    const request = event.request;
    const cache = await caches.open(CACHE);
    const network = fetch(request).then(async response => {
        if (response.ok) {
            const headers = new Headers(response.headers);
            headers.set("X-Saved-At", new Date().toISOString());
            await cache.put(request, new Response(await response.clone().blob(), { status: response.status, headers }));
        }
        return response;
    });
    event.waitUntil(network.catch(() => null));        // keeps saving after a slow answer was replaced

    const slow = new Promise(resolve => setTimeout(resolve, SLOW_MS, "slow"));
    try {
        const first = await Promise.race([network, slow]);
        if (first !== "slow") return first;
    } catch (e) { /* no connection */ }

    // a page's HTML is the same whatever its query (?tab=…, ?q=…: read by the page's script), so
    // any saved copy of the page will do
    const saved = await cache.match(request) ||
        (request.mode === "navigate" && await cache.match(request, { ignoreSearch: true }));
    if (saved) {
        if (tellPage) tellSaved(event.clientId, saved.headers.get("X-Saved-At"));
        return saved;
    }
    try {
        return await network;        // slow, but nothing saved to show instead
    } catch (e) {
        return (fallback && await cache.match(fallback)) || Response.error();
    }
}

async function cacheFirst(request) {
    const saved = await caches.match(request);
    if (saved) return saved;
    const response = await fetch(request);
    // only real (CORS) answers: the pages check CDN files against their hash, which an opaque copy can't pass
    if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE).then(cache => cache.put(request, copy));
    }
    return response;
}

async function tellSaved(clientId, savedAt) {
    const client = clientId && await self.clients.get(clientId);
    client?.postMessage({ type: "saved-answer", savedAt });
}
