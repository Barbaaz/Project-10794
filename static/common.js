/*
 * Shared by every page (loaded first, in <head>): browser storage that never throws,
 * HTML escaping, store names, the light / dark theme, the header's account area and the
 * app on a phone (service worker, install button).
 */

// Browser storage can be missing or refuse access (private windows, blocked site data):
// reading then gives the fallback, saving does nothing.
function saved(key, fallback = null, storage = "localStorage") {
    try { return window[storage].getItem(key) ?? fallback; } catch (e) { return fallback; }
}

// A saved list (or object): the fallback when missing, unreadable or of another kind
function savedJSON(key, fallback, storage = "localStorage") {
    try {
        const value = JSON.parse(window[storage].getItem(key));
        return value !== null && Array.isArray(value) === Array.isArray(fallback) ? value : fallback;
    } catch (e) {
        return fallback;
    }
}

function save(key, value, storage = "localStorage") {
    try { window[storage].setItem(key, typeof value === "string" ? value : JSON.stringify(value)); } catch (e) {}
}

// Text for HTML, in content and in attributes (title="…", value="…"): quotes too, or a display
// name like x" onmouseover="… would add its own attribute (tests/test_escaping.py)
const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
function esc(text) {
    return String(text ?? "").replace(/[&<>"']/g, c => ESCAPES[c]);
}

// "@name"; "utilizador removido" for an account deleted since (no username or page any more)
// A card's picture: IGDB's flat cover fills the 3:4 frame; a store's photo (a special edition's box, a
// game IGDB lacks) is shown whole on white, never cut (user, 2026-10-12: "normalize the images")
function coverClass(url) {
    return url && !url.includes("images.igdb.com") ? "store-photo" : "";
}

// Line icons drawn in the text's colour (user, 2026-10-13: no emojis on the site); shapes after Lucide (ISC)
const ICONS = {
    bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    tag: '<path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.42l8.7 8.7a2.43 2.43 0 0 0 3.42 0l6.58-6.58a2.43 2.43 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r="1"/>',
    library: '<path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/>',
    user: '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
    star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
    globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    lock: '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    gamepad: '<line x1="6" y1="11" x2="10" y2="11"/><line x1="8" y1="9" x2="8" y2="13"/><line x1="15" y1="12" x2="15.01" y2="12"/><line x1="18" y1="10" x2="18.01" y2="10"/><path d="M17.32 5H6.68a4 4 0 0 0-3.98 3.59l-.92 8.31A3 3 0 0 0 4.77 20.2a3 3 0 0 0 2.73-1.75L8.6 16h6.8l1.1 2.45a3 3 0 0 0 5.72-1.55l-.92-8.31A4 4 0 0 0 17.32 5z"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
};

// filled: the shape painted in too (a wished game's star)
function icon(name, size = 18, { filled = false } = {}) {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="${filled ? "currentColor" : "none"}"
        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"
        class="svg-icon">${ICONS[name]}</svg>`;
}

// A user's picture (their profile picture, else a drawn figure), `size` px round
function avatarImage(url, size = 32) {
    return url ? `<img src="${esc(url)}" alt="" class="avatar" width="${size}" height="${size}">`
               : `<span class="avatar avatar-none" style="width: ${size}px; height: ${size}px; ">${icon("user", Math.round(size * .55))}</span>`;
}

function userLabel(username) {
    return username ? `@${username}` : t("deleted_user");
}

// The same, linked to the user's page
function userLink(username) {
    return username ? `<a href="/user/${encodeURIComponent(username)}">@${esc(username)}</a>` : esc(t("deleted_user"));
}

// `stores` ({slug: store}) is filled by each page from /api/stores
function storeName(slug) {
    return stores[slug]?.name || slug;
}

// Theme: the visitor's choice, else the system's. A page that draws with theme colours
// (the game page's charts) defines onThemeChange() to redraw.
function savedTheme() {
    return saved("theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

function toggleDark() {
    const next = document.documentElement.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-bs-theme", next);
    save("theme", next);
    if (typeof onThemeChange === "function") onThemeChange();
}

document.documentElement.setAttribute("data-bs-theme", savedTheme());

// Every theme button (the header's, the account menu's on a phone): one listener, no onclick="…" (the CSP)
document.addEventListener("click", event => {
    if (event.target.closest("[data-toggle-dark]")) toggleDark();
});

// Calls to our API that change something: JSON in and out, with the header the server
// requires on such requests (it can't be added by another site: app/web.py).
// Resolves to {ok, status, data}; data.error is a code for t("error_" + code).
async function api(path, { method = "POST", body } = {}) {
    const response = await fetch(path, {
        method,
        headers: { "X-Requested-With": "fetch", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
        body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await response.json(); } catch (e) {}
    return { ok: response.ok, status: response.status, data };
}

// The account part of the header (the same on every page): "Entrar" when logged out; logged in,
// Vender / Coleção (named from large width up, icons on a phone), then the star (wishlist), the inbox
// (messages) and the bell (notifications) side by side and the account
// menu (my account, profile, moderation, language and theme on a phone, log out).
// After logging in / out, the page reloads so everything shows the right state.
let currentUser = null;

async function renderAccountArea() {
    const box = document.getElementById("account-area");
    if (!box) return;
    try { currentUser = await fetch("/api/auth/me").then(r => r.json()); } catch (e) { currentUser = null; }
    document.body.classList.toggle("logged-in", Boolean(currentUser));
    if (!currentUser) {
        const next = encodeURIComponent(location.pathname + location.search);
        box.innerHTML = `<a href="/account?next=${next}" class="btn btn-sm btn-primary">${t("log_in")}</a>`;
        return;
    }
    const staff = ["moderator", "admin"].includes(currentUser.role);
    const name = currentUser.username || currentUser.display_name;
    const navButton = (href, icon, label, extra = "", iconOnly = false) => `
        <a href="${href}" class="btn btn-sm header-link position-relative${iconOnly ? " icon-only" : ""}" ${extra}
           title="${esc(label)}" aria-label="${esc(label)}"><span class="icon">${icon}</span>${iconOnly ? "" : `<span class="d-none d-lg-inline">${esc(label)}</span>`}</a>`;
    box.innerHTML = `
        ${navButton("/sell", icon("tag"), t("nav_sell"))}
        ${navButton("/collection", icon("library"), t("nav_collection"), 'id="collection-link"')}
        ${navButton("/wishlist", icon("star"), t("nav_wishlist"), 'id="wishlist-link"', true)}
        ${navButton("/messages", icon("inbox"), t("messages"), 'id="messages-link"', true)}
        <div class="notifications position-relative">
            <button type="button" class="btn btn-sm header-link icon-only position-relative" id="notifications-btn" aria-expanded="false"
                    aria-controls="notifications-panel" title="${esc(t("notifications"))}" aria-label="${esc(t("notifications"))}"><span class="icon">${icon("bell")}</span></button>
            <div class="dropdown-menu shadow notifications-panel" id="notifications-panel"></div>
        </div>
        <div class="account-menu position-relative">
            <button type="button" class="btn btn-sm header-link" id="account-menu-btn" aria-haspopup="menu" aria-expanded="false"
                    aria-controls="account-menu" title="${esc(t("account_menu"))}"><span class="icon">${currentUser.avatar ? avatarImage(currentUser.avatar, 22) : icon("user")}</span><span class="d-none d-sm-inline ms-1">${esc(name)}</span> ▾</button>
            <div class="dropdown-menu shadow" id="account-menu" role="menu">
                <span class="dropdown-header">@${esc(name)}</span>
                <a class="dropdown-item" role="menuitem" href="/account">⚙️ ${t("settings_title")}</a>
                <a class="dropdown-item" role="menuitem" href="/user/${encodeURIComponent(currentUser.username || "")}">${t("my_profile")}</a>
                ${staff ? `<a class="dropdown-item" role="menuitem" href="/admin">🛡️ ${t("mod_title")}</a>` : ""}
                <div class="d-sm-none">
                    <hr class="dropdown-divider">
                    <button type="button" class="dropdown-item" role="menuitem" data-switch-lang>${t("lang_other")}</button>
                    <button type="button" class="dropdown-item" role="menuitem" data-toggle-dark>${icon("moon", 16)} ${t("dark_mode")}</button>
                </div>
                <hr class="dropdown-divider">
                <button type="button" class="dropdown-item" role="menuitem" id="logout-btn">${t("log_out")}</button>
            </div>
        </div>`;
    showUnreadCount();
    showPendingRatings();
    showNotifications();
    bindAccountMenu(box);
    box.querySelector("#logout-btn").onclick = async () => {
        await api("/api/auth/logout");
        location.reload();
    };
    box.querySelector("[data-switch-lang]").onclick = () => {
        save("lang", LANG === "pt" ? "en" : "pt");
        location.reload();
    };
}

// The account menu: opens on click; Esc, Tab out or a click elsewhere closes it; arrows move
function bindAccountMenu(box) {
    const wrap = box.querySelector(".account-menu");
    const button = box.querySelector("#account-menu-btn");
    const menu = box.querySelector("#account-menu");
    const items = () => [...menu.querySelectorAll(".dropdown-item")].filter(i => i.offsetParent !== null);
    const setOpen = (open, focus) => {
        menu.classList.toggle("show", open);
        button.setAttribute("aria-expanded", open);
        if (open && focus) items()[0]?.focus();
        if (!open && focus) button.focus();
    };
    button.onclick = () => setOpen(!menu.classList.contains("show"), true);
    document.addEventListener("click", e => { if (!wrap.contains(e.target)) setOpen(false); });
    menu.addEventListener("keydown", e => {
        if (e.key === "Escape") return setOpen(false, true);
        if (e.key === "Tab") return setOpen(false);
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            const list = items();
            const next = list.indexOf(document.activeElement) + (e.key === "ArrowDown" ? 1 : -1);
            list[(next + list.length) % list.length].focus();
        }
    });
}

// The number of unread messages on the inbox button (the messages page calls it again as it reads)
async function showUnreadCount() {
    const link = document.getElementById("messages-link");
    if (!link) return;
    const { count } = await fetch("/api/conversations/unread").then(r => r.json()).catch(() => ({ count: 0 }));
    link.querySelector(".badge")?.remove();
    if (count) {
        link.insertAdjacentHTML("beforeend", `<span class="position-absolute top-0 start-100 translate-middle badge rounded-pill text-bg-danger">${count}</span>`);
        link.setAttribute("aria-label", `${t("messages")} (${t("unread_count", { count })})`);
    }
}

// --- Notifications (user, 2026-10-13): the bell button lists what's waiting for the user ---------
// Wishes that are a good deal now (on sale, at the historical low, cheaper than when added; collection_service.good_deals)
// and trades to rate. The number counts the deals not seen yet (this browser remembers which, by price)
// plus the ratings to give; opening the panel marks the deals seen.
const SEEN_DEALS = "seen-deals";

async function showNotifications() {
    const button = document.getElementById("notifications-btn");
    const panel = document.getElementById("notifications-panel");
    if (!button) return;
    const [deals, ratings] = await Promise.all([
        fetch("/api/collection/deals").then(r => r.ok ? r.json() : { items: [] }).catch(() => ({ items: [] })),
        fetch("/api/ratings/pending").then(r => r.ok ? r.json() : []).catch(() => []),
    ]);
    const key = d => `${d.id}:${d.best_price}`;
    const seen = new Set(savedJSON(SEEN_DEALS, []));
    const fresh = deals.items.filter(d => !seen.has(key(d)));
    const count = fresh.length + ratings.length;

    // why it's there (collection_service.deal_reason, by the user's settings)
    const why = d => d.reason === "sale" ? `−${d.discount}%`
        : d.reason === "low" ? t("notif_low")
        : d.reason === "drop" ? t("notif_price_drop", { amount: eur.format(d.price_drop) }) : "";
    const deal = d => `
        <a class="dropdown-item notif-item d-flex gap-2 align-items-center" href="/game/${d.game_id}">
            <img src="${esc(d.image || "")}" class="${coverClass(d.image)}" alt="">
            <span class="flex-grow-1 min-w-0 text-wrap">
                <span class="d-block fw-semibold">${esc(localName(d) || "")}</span>
                <span class="d-block small text-body-secondary">${esc(d.platform || "")}
                    ${d.best_price != null ? ` · <strong class="text-body">${eur.format(d.best_price)}</strong>` : ""}
                    ${why(d) ? ` · <span class="text-success">${esc(why(d))}</span>` : ""}</span>
            </span>
            ${seen.has(key(d)) ? "" : `<span class="badge text-bg-primary">${esc(t("notif_new"))}</span>`}
        </a>`;
    const rating = p => `
        <a class="dropdown-item small text-wrap" href="/messages?c=${p.conversation_id}">${esc(t("rate_link", { user: userLabel(p.other_username), game: p.title }))}</a>`;
    panel.innerHTML = `
        <h2 class="dropdown-header h6 mb-0">${esc(t("notifications"))}</h2>
        ${ratings.length ? `<div class="dropdown-header small pt-0">${esc(t("notif_ratings"))}</div>${ratings.map(rating).join("")}` : ""}
        ${deals.items.length ? `<div class="dropdown-header small pt-2">${esc(t("notif_deals"))}</div>
            <div class="notif-list">${deals.items.map(deal).join("")}</div>
            <hr class="dropdown-divider"><a class="dropdown-item small" href="/wishlist">${esc(t("notif_see_wishlist"))}</a>` : ""}
        ${count || deals.items.length ? "" : `<p class="px-3 py-2 mb-0 small text-body-secondary text-wrap">${esc(t(deals.off ? "notif_off" : "notif_none"))}</p>`}
        <a class="dropdown-item small text-body-secondary" href="/account#notifications">${esc(t("notif_settings"))}</a>`;

    button.querySelector(".badge")?.remove();
    if (count) {
        button.insertAdjacentHTML("beforeend", `<span class="position-absolute top-0 start-100 translate-middle badge rounded-pill text-bg-danger">${count}</span>`);
        button.setAttribute("aria-label", `${t("notifications")} (${t("notif_count", { count })})`);
    }
    const setOpen = (open, focus) => {
        panel.classList.toggle("show", open);
        button.setAttribute("aria-expanded", open);
        if (open) {
            panel.style.top = `${button.getBoundingClientRect().bottom + 4}px`;     // phones: fixed under the button (common.css)
            // seen: the deals' badge goes; the ratings stay counted until given
            save(SEEN_DEALS, deals.items.map(key));
            button.querySelector(".badge")?.remove();
            if (ratings.length) button.insertAdjacentHTML("beforeend",
                `<span class="position-absolute top-0 start-100 translate-middle badge rounded-pill text-bg-danger">${ratings.length}</span>`);
            button.setAttribute("aria-label", ratings.length ? `${t("notifications")} (${t("notif_count", { count: ratings.length })})` : t("notifications"));
        }
        if (!open && focus) button.focus();
    };
    button.onclick = () => setOpen(!panel.classList.contains("show"));
    // the click's path as it happened: opening removes the badge, which may be what was clicked
    document.addEventListener("click", e => { if (!e.composedPath().includes(button.parentElement)) setOpen(false); });
    panel.addEventListener("keydown", e => { if (e.key === "Escape") setOpen(false, true); });
    button.addEventListener("keydown", e => { if (e.key === "Escape") setOpen(false); });
}

// --- The app on a phone (static/sw.js, static/manifest.webmanifest) ---------------------------

// The service worker: pages open on a weak connection or none, from what was saved on the last visit
if ("serviceWorker" in navigator) {
    addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
    navigator.serviceWorker.addEventListener("message", event => {
        if (event.data?.type === "saved-answer") whenReady(() => showSavedNotice(event.data.savedAt));
    });
}

function whenReady(run) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
    else run();
}

// No connection, so the page shows saved prices: say so, with when they were saved (the oldest)
function showSavedNotice(savedAt) {
    const existing = document.getElementById("saved-notice");
    if (existing && existing.dataset.savedAt <= (savedAt || "")) return;
    existing?.remove();
    const when = savedAt ? new Date(savedAt).toLocaleString(LOCALE, { dateStyle: "short", timeStyle: "short" }) : "?";
    const notice = document.createElement("div");
    notice.id = "saved-notice";
    notice.dataset.savedAt = savedAt || "";
    notice.className = "alert alert-warning py-2 small d-flex flex-wrap align-items-center gap-2";
    notice.setAttribute("role", "status");
    notice.innerHTML = `<span>📡 ${esc(t("offline_notice", { time: when }))}</span>
        <button type="button" class="btn btn-sm btn-warning ms-auto">${esc(t("offline_retry"))}</button>`;
    notice.querySelector("button").onclick = () => location.reload();
    const container = document.querySelector("body > .container, body > .container-xl, body > .container-xxl");
    if (container) container.querySelector(":scope > div")?.after(notice);
    else document.body.prepend(notice);
}

// "Install app" in the header, where the browser offers it (Android / desktop Chrome and Edge;
// on an iPhone: Share → Add to Home Screen, which needs nothing from the page)
let installPrompt = null;
addEventListener("beforeinstallprompt", event => {
    event.preventDefault();
    installPrompt = event;
    whenReady(showInstallButton);
});
addEventListener("appinstalled", () => document.getElementById("install-btn")?.remove());

function showInstallButton() {
    const box = document.getElementById("account-area");
    if (!box || !installPrompt || document.getElementById("install-btn")) return;
    const button = document.createElement("button");
    button.type = "button";
    button.id = "install-btn";
    button.className = "btn btn-sm btn-success";
    // only the icon on a phone's narrow header
    button.innerHTML = `📲<span class="d-none d-md-inline"> ${esc(t("install_app"))}</span>`;
    button.title = t("install_app_title");
    button.setAttribute("aria-label", t("install_app_title"));
    button.onclick = async () => {
        installPrompt.prompt();
        await installPrompt.userChoice;
        installPrompt = null;
        button.remove();
    };
    box.before(button);
}

function forget(key, storage = "localStorage") {
    try { window[storage].removeItem(key); } catch (e) {}
}

// Ratings still to give (completed purchases): a reminder at the top of every page, red once one
// is overdue (14 days), which blocks buying and selling until it's given (app/services/rating_service.py)
async function showPendingRatings() {
    document.getElementById("ratings-banner")?.remove();
    if (!currentUser) return;
    const pending = await fetch("/api/ratings/pending").then(r => r.ok ? r.json() : []).catch(() => []);
    if (!pending.length) return;
    const overdue = pending.some(p => p.overdue);
    const banner = document.createElement("div");
    banner.id = "ratings-banner";
    banner.className = `alert ${overdue ? "alert-danger" : "alert-warning"} py-2 small`;
    banner.setAttribute("role", "status");
    banner.innerHTML = `<strong>${esc(t(overdue ? "ratings_overdue_title" : "ratings_pending_title", { count: pending.length }))}</strong>
        ${pending.map(p => `<a href="/messages?c=${p.conversation_id}" class="ms-2">${esc(t("rate_link", { user: userLabel(p.other_username), game: p.title }))}</a>`).join("")}`;
    const container = document.querySelector("body > .container, body > .container-xl, body > .container-xxl");
    container?.querySelector(":scope > div")?.after(banner);
}

// --- Back to the top (user, 2026-10-13) ---------------------------------------------------------
// A round button at the bottom right once the visitor has scrolled more than a screen and a half
whenReady(() => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-primary shadow back-to-top";
    button.setAttribute("aria-label", t("back_to_top"));
    button.title = t("back_to_top");
    button.textContent = "↑";
    button.onclick = () => {
        const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
        scrollTo({ top: 0, behavior: still ? "auto" : "smooth" });
    };
    document.body.appendChild(button);
    const update = () => button.classList.toggle("shown", scrollY > innerHeight * 1.5);
    addEventListener("scroll", update, { passive: true });
    update();
});
