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
