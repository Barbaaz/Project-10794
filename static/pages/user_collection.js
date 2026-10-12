// A user's public collection as a grid of covers (templates/user_collection.html; user, 2026-10-12: its
// own page, not a list inside the profile). Read-only: the owner edits theirs at /collection
const USERNAME = document.body.dataset.username;
const STATUSES = ["finished", "playing", "backlog", "paused", "dropped", "owned"];
const SORTS = {
    name: (a, b) => (localName(a) || "").localeCompare(localName(b) || "", LOCALE),
    hours: (a, b) => (b.hours ?? -1) - (a.hours ?? -1),
};
let items = [], platform = "";

function card(i) {
    const facts = [
        i.status && i.status !== "owned" ? `<span class="badge text-bg-secondary">${esc(t(`status_play_${i.status}`))}</span>` : "",
        i.format ? `<span>${esc(t(`format_${i.format}`))}</span>` : "",
        i.hours ? `<span>${fmtNumber(i.hours)} h</span>` : "",
        i.achievements_total ? `<span>🏆 ${i.achievements ?? 0}/${i.achievements_total}</span>` : "",
        i.platinum ? `<span class="badge text-bg-info">${esc(t("collection_platinum"))}</span>` : "",
    ].filter(Boolean).join("");
    return `
        <div class="col"><div class="card h-100 overflow-hidden">
            <a href="/game/${i.game_id}" tabindex="-1" aria-hidden="true"><img class="item-cover" src="${esc(i.image || "")}" alt="" loading="lazy"></a>
            <div class="card-body p-2 min-w-0">
                <a href="/game/${i.game_id}" class="item-title fw-semibold small link-body-emphasis text-decoration-none">${esc(localName(i) || "")}</a>
                <div class="small text-body-secondary">${esc(i.platform_name || "")}</div>
                ${facts ? `<div class="item-facts small mt-1">${facts}</div>` : ""}
            </div>
        </div></div>`;
}

function render() {
    const status = document.getElementById("filter-status").value;
    const words = document.getElementById("filter-text").value.toLowerCase().split(/\s+/).filter(Boolean);
    const listed = items.filter(i => (!status || i.status === status)
        && words.every(w => `${i.name || ""} ${i.name_en || ""}`.toLowerCase().includes(w)));
    // one button per platform, with how many (as on /collection)
    const counts = {};
    listed.forEach(i => counts[i.platform_name || "?"] = (counts[i.platform_name || "?"] || 0) + 1);
    const names = Object.keys(counts).sort((a, b) => counts[b] - counts[a] || a.localeCompare(b, LOCALE));
    if (platform && !counts[platform]) platform = "";
    const box = document.getElementById("filter-platforms");
    box.classList.toggle("d-none", names.length < 2);
    box.innerHTML = [["", t("collection_all_platforms"), listed.length], ...names.map(n => [n, n, counts[n]])].map(([value, label, n]) =>
        `<button type="button" class="chip-btn" data-platform="${esc(value)}" aria-pressed="${platform === value}">${esc(label)} <span class="opacity-75">${n}</span></button>`).join("");
    box.querySelectorAll("[data-platform]").forEach(b => b.onclick = () => { platform = b.dataset.platform; render(); });
    const shown = listed.filter(i => !platform || (i.platform_name || "?") === platform)
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
    const status = document.getElementById("filter-status");
    status.innerHTML = `<option value="">${t("collection_all_statuses")}</option>`
        + STATUSES.map(s => `<option value="${s}">${t(`status_play_${s}`)}</option>`).join("");
    document.getElementById("sort").innerHTML = Object.keys(SORTS).map(s => `<option value="${s}">${t(`sort_${s}`)}</option>`).join("");
    ["filter-text", "filter-status", "sort"].forEach(id => document.getElementById(id).oninput = render);
    render();
    document.getElementById("content").classList.remove("d-none");
}
applyI18n();
load();
