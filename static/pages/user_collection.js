// A user's public collection as a grid of covers (templates/user_collection.html; user, 2026-10-12: its
// own page, not a list inside the profile). Read-only: the owner edits theirs at /collection
const USERNAME = document.body.dataset.username;
const SORTS = {
    name: (a, b) => (localName(a) || "").localeCompare(localName(b) || "", LOCALE),
    hours: (a, b) => (b.hours ?? -1) - (a.hours ?? -1),
};
let items = [];
const chosen = {};                     // the sidebar's ticked boxes (collection_grid.js)

function card(i) {
    return `
        <div class="col"><div class="card h-100 overflow-hidden">
            <a href="/game/${i.game_id}" tabindex="-1" aria-hidden="true"><img class="item-cover" src="${esc(i.image || "")}" alt="" loading="lazy"></a>
            <div class="card-body p-2 min-w-0">
                <a href="/game/${i.game_id}" class="item-title fw-semibold small link-body-emphasis text-decoration-none">${esc(localName(i) || "")}</a>
                <div class="item-line small text-body-secondary">${esc(i.platform_name || "")}</div>
                <div class="mt-1">${factRows(i)}</div>
            </div>
        </div></div>`;
}

function render() {
    const words = document.getElementById("filter-text").value.toLowerCase().split(/\s+/).filter(Boolean);
    const listed = items.filter(i => words.every(w => `${i.name || ""} ${i.name_en || ""}`.toLowerCase().includes(w)));
    const groups = ownedFilterGroups(listed);
    const sidebar = document.getElementById("filters");
    renderFilters(sidebar, listed, groups, chosen, render);
    filtersToggle(document.getElementById("filters-toggle"), sidebar, chosen);
    const shown = filterItems(listed, groups, chosen)
        .sort((a, b) => SORTS[document.getElementById("sort").value](a, b) || SORTS.name(a, b));
    document.getElementById("items").innerHTML = shown.map(card).join("");
    document.getElementById("empty").classList.toggle("d-none", shown.length > 0);
}

async function load() {
    await renderAccountArea();
    const response = await fetch(`/api/users/${encodeURIComponent(USERNAME)}/collection`);
    document.getElementById("loading").classList.add("d-none");
    if (!response.ok) return document.getElementById("error").classList.remove("d-none");
    const data = await response.json();
    items = data.items.filter(i => i.kind === "owned");
    const who = userLabel(USERNAME);
    document.title = `${t("user_collection_title", { user: who })} · SaveGame`;
    document.getElementById("title").innerHTML = esc(t("user_collection_title", { user: "\u0000" })).replace("\u0000",
        `<a href="/user/${encodeURIComponent(USERNAME)}">${esc(who)}</a>`);
    document.getElementById("summary").textContent = t("profile_collection_summary",
        { owned: data.stats.owned, completed: data.stats.completed, wishlist: data.stats.wishlist });
    if (currentUser && currentUser.username?.toLowerCase() !== USERNAME.toLowerCase()) {
        const link = document.getElementById("compare-link");
        link.href = `/compare/${encodeURIComponent(USERNAME)}`;
        link.classList.remove("d-none");
    }
    document.getElementById("sort").innerHTML = Object.keys(SORTS).map(s => `<option value="${s}">${t(`sort_${s}`)}</option>`).join("");
    ["filter-text", "sort"].forEach(id => document.getElementById(id).oninput = render);
    render();
    document.getElementById("content").classList.remove("d-none");
}
applyI18n();
load();
