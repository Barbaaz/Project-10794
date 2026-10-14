// Shared by the two collection pages (/collection, /user/<name>/collection): the sidebar's checkbox
// filters (user, 2026-10-12: "a sidebar with checkbox filters") and the cards' rows.

// groups: [{key, title, options: [{value, label}], test(item, value)}]; selected: {key: Set of values}.
// In a group a game matches any ticked box, across groups every group; each box counts the games it
// would show with the other groups' boxes as they are.
function passesFilters(item, groups, selected, skip = null) {
    return groups.every(g => g.key === skip || !selected[g.key]?.size || [...selected[g.key]].some(v => g.test(item, v)));
}

function filterItems(items, groups, selected) {
    return items.filter(i => passesFilters(i, groups, selected));
}

function filtersChosen(selected) {
    return Object.values(selected).reduce((n, set) => n + set.size, 0);
}

// The sidebar's boxes (a box with no game is left out, unless it's ticked); onChange() redraws the page
function renderFilters(box, items, groups, selected, onChange) {
    const focused = document.activeElement?.closest?.("[data-group]");
    const keep = focused && box.contains(focused) ? [focused.dataset.group, focused.value] : null;
    box.innerHTML = groups.map(g => {
        const base = items.filter(i => passesFilters(i, groups, selected, g.key));
        const options = g.options.map(o => ({ ...o, n: base.filter(i => g.test(i, o.value)).length }))
            .filter(o => o.n || selected[g.key]?.has(o.value));
        if (!options.length) return "";
        return `
            <fieldset class="mb-3">
                <legend class="filter-title">${esc(g.title)}</legend>
                ${options.map((o, i) => `
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="filter-${g.key}-${i}" data-group="${g.key}"
                               value="${esc(o.value)}" ${selected[g.key]?.has(o.value) ? "checked" : ""}>
                        <label class="form-check-label small d-flex justify-content-between gap-2" for="filter-${g.key}-${i}">
                            <span>${esc(o.label)}</span><span class="text-body-secondary">${o.n}</span></label>
                    </div>`).join("")}
            </fieldset>`;
    }).join("") + (filtersChosen(selected)
        ? `<button type="button" class="btn btn-sm btn-link px-0" data-clear-filters>${esc(t("filters_clear"))}</button>` : "");
    box.querySelectorAll("[data-group]").forEach(input => input.onchange = () => {
        const set = selected[input.dataset.group] ||= new Set();
        input.checked ? set.add(input.value) : set.delete(input.value);
        onChange();
    });
    const clear = box.querySelector("[data-clear-filters]");
    if (clear) clear.onclick = () => { Object.values(selected).forEach(set => set.clear()); onChange(); };
    if (keep) [...box.querySelectorAll("[data-group]")]          // redrawn: the box just ticked keeps the focus
        .find(i => i.dataset.group === keep[0] && i.value === keep[1])?.focus();
}

// The platforms in a list, most games first
function platformOptions(items) {
    const counts = {};
    items.forEach(i => counts[i.platform_name || "?"] = (counts[i.platform_name || "?"] || 0) + 1);
    return Object.keys(counts).sort((a, b) => counts[b] - counts[a] || a.localeCompare(b, LOCALE)).map(n => ({ value: n, label: n }));
}

const platformGroup = items => ({ key: "platform", title: t("collection_platforms"), options: platformOptions(items),
                                  test: (i, v) => (i.platform_name || "?") === v });

// The owned games' groups (both pages)
const PLAY_STATUSES = ["finished", "playing", "backlog", "paused", "dropped", "owned"];
function ownedFilterGroups(items) {
    return [
        platformGroup(items),
        { key: "status", title: t("collection_status"), options: PLAY_STATUSES.map(s => ({ value: s, label: t(`status_play_${s}`) })),
          test: (i, v) => i.status === v },
        { key: "format", title: t("collection_format"), options: ["physical", "digital"].map(f => ({ value: f, label: t(`format_${f}`) })),
          test: (i, v) => (i.format || "physical") === v },
        { key: "more", title: t("filters_more"), options: [
            { value: "trophies", label: t("filters_with_trophies") }, { value: "platinum", label: t("collection_platinum") },
            { value: "hours", label: t("filters_with_hours") }],
          test: (i, v) => v === "trophies" ? !!i.achievements_total : v === "platinum" ? !!i.platinum : !!i.hours },
    ];
}

// "Filtros (2)" on a phone / tablet, where the sidebar opens above the grid
function filtersToggle(button, sidebar, selected) {
    const n = filtersChosen(selected);
    button.textContent = n ? `${t("filters")} (${n})` : t("filters");
    button.onclick = () => button.setAttribute("aria-expanded", sidebar.classList.toggle("open"));
}

// "Terminado" and "Platina" over the cover's top corners (user, 2026-10-12); outside the cover's link,
// which screen readers skip, so they're read
// Each play status's look, the same on the cards and in the edit window (user, 2026-10-12: every status a
// badge); "owned" (no status chosen) has none
const STATUS_LOOK = {
    finished: { icon: "check", css: "status-finished" }, playing: { icon: "play", css: "status-playing" },
    backlog: { icon: "hourglass", css: "status-backlog" }, paused: { icon: "pause", css: "status-paused" },
    dropped: { icon: "x", css: "status-dropped" }, owned: { icon: "", css: "status-owned" },
};

function statusBadge(status) {
    const look = STATUS_LOOK[status];
    return look && status !== "owned" ? `<span class="badge ${look.css}">${icon(look.icon, 12)} ${esc(t(`status_play_${status}`))}</span>` : "";
}

function coverBadges(item) {
    const status = statusBadge(item.status);
    const platinum = item.platinum ? `<span class="badge cover-platinum">${icon("trophy", 12)} ${esc(t("collection_platinum"))}</span>` : "";
    return status || platinum ? `<div class="cover-badges">${status || "<span></span>"}${platinum}</div>` : "";
}

// A card's facts in fixed rows, so the cards' rows line up: the format; hours, trophies, DLC, score (the status
// and the platinum are on the cover)
function factRows(item) {
    const first = `<span>${esc(t(`format_${item.format || "physical"}`))}</span>`;
    const second = [
        item.hours ? `<span>${icon("clock", 13)} ${fmtNumber(item.hours)} h</span>` : "",
        item.achievements_total ? `<span>${icon("trophy", 13)} ${item.achievements ?? 0}/${item.achievements_total}</span>` : "",
        item.dlc?.total ? `<span>${esc(t("collection_dlc_count", item.dlc))}</span>` : "",
        item.score ? `<span>★ ${item.score}/10</span>` : "",
    ].join("");
    return `<div class="item-facts small">${first}</div><div class="item-facts small">${second}</div>`;
}
