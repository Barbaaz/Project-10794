/*
 * Shared by both pages (loaded first, in <head>): browser storage that never throws,
 * HTML escaping, store names and the light / dark theme.
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

function esc(text) {
    const div = document.createElement("div");
    div.textContent = text ?? "";
    return div.innerHTML;
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

// The account part of the header: "Entrar" when logged out, the username and "Sair" when logged in.
// After logging in / out, the page reloads so everything shows the right state.
let currentUser = null;

async function renderAccountArea() {
    const box = document.getElementById("account-area");
    if (!box) return;
    try { currentUser = await fetch("/api/auth/me").then(r => r.json()); } catch (e) { currentUser = null; }
    if (!currentUser) {
        const next = encodeURIComponent(location.pathname + location.search);
        box.innerHTML = `<a href="/account?next=${next}" class="btn btn-sm btn-primary">${t("log_in")}</a>`;
        return;
    }
    box.innerHTML = `
        <a href="/messages" class="btn btn-sm btn-secondary position-relative" id="messages-link"
           title="${esc(t("messages"))}" aria-label="${esc(t("messages"))}">💬</a>
        <a href="/account" class="btn btn-sm btn-secondary" title="${esc(t("my_account"))}">👤 ${esc(currentUser.username || currentUser.display_name)}</a>
        <button type="button" class="btn btn-sm btn-secondary" id="logout-btn">${t("log_out")}</button>`;
    showUnreadCount();
    showPendingRatings();
    box.querySelector("#logout-btn").onclick = async () => {
        await api("/api/auth/logout");
        location.reload();
    };
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
        ${pending.map(p => `<a href="/messages?c=${p.conversation_id}" class="ms-2">${esc(t("rate_link", { user: p.other_username, game: p.title }))}</a>`).join("")}`;
    const container = document.querySelector("body > .container, body > .container-xl, body > .container-xxl");
    container?.querySelector(":scope > div")?.after(banner);
}
