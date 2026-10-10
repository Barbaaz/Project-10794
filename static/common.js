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

// A test copy on demo data (DEMO_MODE, the teste/ launchers): a banner on every page saying the
// prices are a snapshot and how to log in as a made-up user
async function showDemoBanner() {
    let demo = null;
    try { demo = await fetch("/api/demo").then(r => r.json()); } catch (e) { return; }
    if (!demo?.demo) return;
    const date = demo.collected_at ? new Date(demo.collected_at).toLocaleDateString(LOCALE) : "?";
    const banner = document.createElement("div");
    banner.className = "alert alert-info rounded-0 border-0 mb-0 py-2 px-3 small text-center";
    banner.setAttribute("role", "note");
    banner.innerHTML = t("demo_banner", { date: esc(date) });
    document.body.prepend(banner);
}

document.addEventListener("DOMContentLoaded", showDemoBanner);
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
// Vender / Mensagens / Coleção (named from large width up, icons on a phone) and the account
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
    const navButton = (href, icon, label, extra = "") => `
        <a href="${href}" class="btn btn-sm header-link position-relative" ${extra}
           title="${esc(label)}" aria-label="${esc(label)}"><span class="icon">${icon}</span><span class="d-none d-lg-inline">${esc(label)}</span></a>`;
    box.innerHTML = `
        ${navButton("/sell", "🏷️", t("nav_sell"))}
        ${navButton("/messages", "💬", t("messages"), 'id="messages-link"')}
        ${navButton("/collection", "📚", t("nav_collection"), 'id="collection-link"')}
        <div class="account-menu position-relative">
            <button type="button" class="btn btn-sm header-link" id="account-menu-btn" aria-haspopup="menu" aria-expanded="false"
                    aria-controls="account-menu" title="${esc(t("account_menu"))}"><span class="icon">👤</span><span class="d-none d-sm-inline ms-1">${esc(name)}</span> ▾</button>
            <div class="dropdown-menu shadow" id="account-menu" role="menu">
                <span class="dropdown-header">@${esc(name)}</span>
                <a class="dropdown-item" role="menuitem" href="/account">${t("my_account")}</a>
                <a class="dropdown-item" role="menuitem" href="/user/${encodeURIComponent(currentUser.username || "")}">${t("my_profile")}</a>
                ${staff ? `<a class="dropdown-item" role="menuitem" href="/admin">🛡️ ${t("mod_title")}</a>` : ""}
                <div class="d-sm-none">
                    <hr class="dropdown-divider">
                    <button type="button" class="dropdown-item" role="menuitem" data-switch-lang>${t("lang_other")}</button>
                    <button type="button" class="dropdown-item" role="menuitem" data-toggle-dark>🌙 ${t("dark_mode")}</button>
                </div>
                <hr class="dropdown-divider">
                <button type="button" class="dropdown-item" role="menuitem" id="logout-btn">${t("log_out")}</button>
            </div>
        </div>`;
    showUnreadCount();
    showPendingRatings();
    showWishlistDeals();
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

// The number of unread messages on the 💬 button (the messages page calls it again as it reads)
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

// Wishes that are a good deal now (on sale, at the historical low, cheaper than when added) on the 📚 button
async function showWishlistDeals() {
    const link = document.getElementById("collection-link");
    if (!link) return;
    const { count } = await fetch("/api/collection/deals").then(r => r.ok ? r.json() : { count: 0 }).catch(() => ({ count: 0 }));
    if (!count) return;
    link.href = "/collection?tab=wishlist";
    link.insertAdjacentHTML("beforeend", `<span class="position-absolute top-0 start-100 translate-middle badge rounded-pill text-bg-success">${count}</span>`);
    link.title = t("wishlist_deals", { count });
    link.setAttribute("aria-label", `${t("collection_title")} (${t("wishlist_deals", { count })})`);
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
