// The collection page (templates/collection.html). A file, not inline: the site's CSP only runs scripts from files.
const STATUSES = ["finished", "playing", "backlog", "paused", "dropped", "owned"];
let data = null;
let kind = new URLSearchParams(location.search).get("tab") === "wishlist" ? "wishlist" : "owned";

function showMessage(ok, text) {
    const box = document.getElementById("message");
    box.className = `alert ${ok ? "alert-success" : "alert-warning"} py-2 small`;
    box.textContent = text;
}

function stat(label, value) {
    return `<div class="card stat"><div class="card-body p-2">
        <div class="small text-body-secondary">${esc(label)}</div><div class="fs-5 fw-semibold">${value}</div></div></div>`;
}

// Only the figures there is something to show for (an empty collection shows the two counts)
function renderStats() {
    const s = data.stats;
    const statuses = STATUSES.filter(x => s.statuses[x]).map(x => `${t(`status_play_${x}`)}: ${s.statuses[x]}`).join(" · ");
    const platforms = s.platforms.map(([p, n]) => `${p}: ${n}`).join(" · ");
    document.getElementById("stats").innerHTML = [
        stat(t("collection_owned_count"), fmtNumber(s.owned)),
        stat(t("collection_wishlist_count"), fmtNumber(s.wishlist)),
        s.owned && stat(t("collection_completed"), `${fmtNumber(s.completed)} <span class="small fw-normal">(${Math.round(100 * s.completed / s.owned)}%)</span>`),
        s.hours && stat(t("collection_hours"), fmtNumber(Math.round(s.hours * 10) / 10)),
        s.achievements_total && stat(t("collection_achievements"),
            `${fmtNumber(s.achievements)} / ${fmtNumber(s.achievements_total)} <span class="small fw-normal">(${Math.round(100 * s.achievements / s.achievements_total)}%)</span>`),
        s.priced_new && stat(t("collection_worth_new"), `${eur.format(s.worth_new)} <span class="small fw-normal text-body-secondary">(${s.priced_new})</span>`),
        s.priced_used && stat(t("collection_worth_used"), `${eur.format(s.worth_used)} <span class="small fw-normal text-body-secondary">(${s.priced_used})</span>`),
    ].filter(Boolean).join("")
        + (platforms ? `<div class="w-100 small text-body-secondary">${esc(platforms)}</div>` : "")
        + (statuses ? `<div class="w-100 small text-body-secondary mt-n2">${esc(statuses)}</div>` : "");
    document.querySelector('[data-kind="owned"]').textContent = `${t("collection_tab_owned")} (${s.owned})`;
    document.querySelector('[data-kind="wishlist"]').textContent = `${t("collection_tab_wishlist")} (${s.wishlist})`;
}

// What it costs now, one fact per line so the cards line up: best store price and store, else "Ver na
// Steam", "À procura" or no price; the cheapest used copy; a wish's badges (on sale, lowest, cheaper)
function priceLine(item) {
    const parts = [];
    if (item.best_price !== null) {
        parts.push(`<span title="${esc(t("collection_best_now"))}"><strong>${eur.format(item.best_price)}</strong> · ${esc(item.best_store)}</span>`);
    } else if (item.steam_app_id) {
        // no store here sells it, but it's on Steam (a PC game; user, 2026-10-11)
        // a button (user, 2026-10-12), without padding top and bottom: it keeps to the card's one line
        parts.push(`<a class="btn btn-sm btn-secondary py-0 px-2" href="https://store.steampowered.com/app/${Number(item.steam_app_id)}/"
                       target="_blank" rel="noopener">${t("collection_on_steam")}</a>`);
    } else if (item.kind === "wishlist" && !item.used) {
        // nobody sells it: "looking for", with an e-mail when a store or a user does (wish_alert_service)
        parts.push(`<span class="badge text-bg-info" title="${esc(t("collection_looking_for_help"))}">${t("collection_looking_for")}</span>`);
    } else {
        parts.push(`<span class="text-body-secondary">${t("collection_no_store_price")}</span>`);
    }
    const used = item.used ? `<a href="/listing/${item.used.listing_id}">${esc(t("used_from", { price: eur.format(item.used.price) }))}</a>` : "";
    const lines = `<div class="item-line small">${parts.join("")}</div><div class="item-line small">${used}</div>`;
    if (item.kind !== "wishlist") return lines;
    const badges = [
        item.on_sale ? `<span class="badge text-bg-danger">${t("tag_on_sale")}${item.discount ? ` −${Math.round(item.discount)}%` : ""}</span>` : "",
        item.at_historical_low ? `<span class="badge text-bg-success">${t("low_badge")}</span>` : "",
        item.price_drop ? `<span class="badge text-bg-warning" title="${esc(t("collection_wished_at", { price: eur.format(item.wish_price) }))}">${t("collection_price_drop", { amount: eur.format(item.price_drop) })}</span>` : "",
    ].join("");
    return lines + `<div class="item-facts small">${badges}</div>`;
}

// What the user wrote about an owned game, in fixed rows (collection_grid.js factRows); the notes are in the
// editor ("Editar")
function ownedFacts(item) {
    return factRows(item);
}

// The edit window's controls (user, 2026-10-12: "more intuitive"): the status and the format as buttons
// (the status in its badge's colour), the progress together (hours, trophies with a bar, the platinum),
// the score as 1-10 buttons, the notes. Each is saved as it changes ("✓ Guardado")
function choices(field, options, current, label) {
    return `<div class="choice-group" role="group" aria-label="${esc(label)}">${options.map(o => `
        <button type="button" class="choice" data-choice="${field}" data-value="${esc(o.value)}" data-on="${o.css || "choice-on"}"
                aria-pressed="${o.value === current}">${o.label}</button>`).join("")}</div>`;
}

function section(title, content) {
    return `<section class="editor-section"><h3 class="editor-title">${esc(title)}</h3>${content}</section>`;
}

function progressBar(item) {
    if (!item.achievements_total) return "";
    const share = Math.min(100, Math.round(100 * (item.achievements || 0) / item.achievements_total));
    return `<div class="d-flex align-items-center gap-2 mt-2"><div class="progress flex-grow-1" style="height: .5rem;" role="progressbar"
                 aria-valuenow="${share}" aria-valuemin="0" aria-valuemax="100"><div class="progress-bar" style="width: ${share}%"></div></div>
            <span class="small text-body-secondary">${share}%</span></div>`;
}

function ownedControls(item) {
    const playstation = (item.platform_name || "").startsWith("PlayStation");
    const statuses = STATUSES.map(s => ({ value: s, css: STATUS_LOOK[s].css,
                                          label: `${STATUS_LOOK[s].icon ? `${STATUS_LOOK[s].icon} ` : ""}${esc(t(`status_play_${s}`))}` }));
    return `
        ${section(t("collection_status"), choices("status", statuses, item.status || "owned", t("collection_status")))}
        ${section(t("collection_format"), choices("format", ["physical", "digital"].map(f => ({ value: f, label: esc(t(`format_${f}`)) })),
                                                  item.format || "physical", t("collection_format")))}
        ${section(t("collection_progress"), `
            <div class="row g-2">
                <div class="col-5"><label class="small text-body-secondary d-block" for="edit-hours">${esc(t("collection_hours"))}</label>
                    <div class="input-group input-group-sm">
                        <input id="edit-hours" type="text" inputmode="decimal" class="form-control" data-field="hours"
                               value="${item.hours === null ? "" : fmtNumber(item.hours)}" placeholder="0"><span class="input-group-text">h</span></div></div>
                <div class="col-7"><span class="small text-body-secondary d-block">${esc(t("collection_trophies"))}</span>
                    <div class="input-group input-group-sm">
                        <input type="number" min="0" class="form-control" data-field="achievements" value="${item.achievements ?? ""}" placeholder="0"
                               aria-label="${esc(t("collection_achievements_done"))}">
                        <span class="input-group-text">/</span>
                        <input type="number" min="0" class="form-control" data-field="achievements_total" value="${item.achievements_total ?? ""}"
                               placeholder="—" aria-label="${esc(t("collection_achievements_total"))}"></div></div>
            </div>
            <div data-progress>${progressBar(item)}</div>
            ${playstation ? `<button type="button" class="choice mt-2" data-toggle="platinum" data-on="cover-platinum"
                                     aria-pressed="${!!item.platinum}">🏆 ${esc(t("collection_platinum"))}</button>` : ""}`)}
        ${section(t("collection_your_score"), `
            ${choices("score", [{ value: "", label: "—" }, ...Array.from({ length: 10 }, (_, i) => ({ value: String(i + 1), label: String(i + 1) }))],
                      item.score ? String(item.score) : "", t("collection_your_score"))}
            <div class="small text-body-secondary mt-1">${esc(t(item.score_locked ? "collection_score_locked" : "collection_score_hint"))}</div>`)}
        ${section(t("collection_notes"), `
            <textarea class="form-control form-control-sm" rows="2" maxlength="1000" data-field="notes"
                      aria-label="${esc(t("collection_notes"))}">${esc(item.notes || "")}</textarea>`)}`;
}

// One item as a card in the grid: cover, name, platform, prices, what the user wrote, buttons
function itemRow(item) {
    const owned = item.kind === "owned";
    return `
        <div class="col">
          <div class="card h-100 item-card overflow-hidden ${item.good_deal ? "border-success border-2" : ""}" data-id="${item.id}">
            <div class="position-relative">
                <a href="/game/${item.game_id}" class="item-cover-link" tabindex="-1" aria-hidden="true"><img class="item-cover" src="${esc(item.image || "")}" alt="" loading="lazy"></a>
                ${coverBadges(item)}
            </div>
            <div class="card-body p-2 d-flex flex-column min-w-0">
                    <a href="/game/${item.game_id}" class="item-title fw-semibold small link-body-emphasis text-decoration-none">${esc(localName(item) || "")}</a>
                    <div class="item-line small text-body-secondary">${esc(item.platform_name || "")}</div>
                    <div class="mt-1">${priceLine(item)}</div>
                    ${owned ? `<div class="mt-1" data-facts>${ownedFacts(item)}</div>` : ""}
                    <div class="item-actions mt-auto pt-2">
                        ${owned ? `<button type="button" class="btn btn-sm btn-secondary" data-action="edit" aria-haspopup="dialog">${t("collection_edit")}</button>` : ""}
                        ${owned
                            // only physical copies can be sold (a digital game can't be handed over)
                            ? (item.format === "digital" ? "" : `<a class="btn btn-sm btn-success" href="/sell?game_id=${item.game_id}&edition_id=${item.edition_id}">${t("collection_sell")}</a>`)
                            : `<button type="button" class="btn btn-sm btn-success" data-action="bought">${t("collection_bought")}</button>`}
                        <button type="button" class="btn btn-sm btn-danger ms-auto" data-action="remove"
                                aria-label="${esc(t("collection_remove"))}" title="${esc(t("collection_remove"))}">✕</button>
                    </div>
            </div>
          </div>
        </div>`;
}

// The sidebar's ticked boxes, one set per tab (collection_grid.js)
const chosen = { owned: {}, wishlist: {} };
function filterGroups(items) {
    if (kind === "owned") return ownedFilterGroups(items);
    return [platformGroup(items),
            { key: "show", title: t("collection_wish_filter"), options: Object.keys(WISH_FILTERS).filter(Boolean)
                  .map(f => ({ value: f, label: t(`wish_filter_${f}`) })), test: (i, v) => WISH_FILTERS[v](i) }];
}

// The order and, on the wishlist, which wishes (user, 2026-10-11: "sort my wishlist and maybe filter it")
// the wishlist also by the discount and the sale price (user, 2026-10-12)
const SORTS = { owned: ["name", "added", "value", "hours"],
                wishlist: ["name", "added", "price_asc", "price_desc", "discount", "sale_price", "drop"] };
const WISH_FILTERS = {
    "": () => true,
    deals: i => i.good_deal,                                     // on sale, at its lowest, or cheaper than when wished
    available: i => i.best_price !== null || !!i.used || !!i.steam_app_id,
    used: i => !!i.used,
    looking: i => i.best_price === null && !i.used && !i.steam_app_id,   // nobody sells it ("À procura")
};
const sortBy = { owned: "name", wishlist: "name" };
const price = i => i.best_price ?? i.used?.price ?? null;
const last = (a, b, value, descending) => {                       // no value: at the end, either way
    const x = value(a), y = value(b);
    if (x === null || y === null) return (x === null) - (y === null);
    return descending ? y - x : x - y;
};
const byName = (a, b) => (localName(a) || "").localeCompare(localName(b) || "", LOCALE);
const ORDER = {
    name: byName,
    added: (a, b) => (b.created_at || "").localeCompare(a.created_at || ""),
    value: (a, b) => last(a, b, price, true),
    hours: (a, b) => last(a, b, i => i.hours ?? null, true),
    price_asc: (a, b) => last(a, b, price, false),
    price_desc: (a, b) => last(a, b, price, true),
    drop: (a, b) => last(a, b, i => i.price_drop ?? null, true),
    discount: (a, b) => last(a, b, i => i.discount ?? null, true),          // not on sale: at the end
    sale_price: (a, b) => last(a, b, i => i.sale_price ?? null, false),
};

function sortOptions() {
    const sort = document.getElementById("sort");
    sort.innerHTML = SORTS[kind].map(s => `<option value="${s}" ${sortBy[kind] === s ? "selected" : ""}>${t(`sort_${s}`)}</option>`).join("");
}

function renderItems() {
    document.querySelectorAll("[data-kind]").forEach(b => {
        b.classList.toggle("active", b.dataset.kind === kind);
        b.setAttribute("aria-selected", b.dataset.kind === kind);
    });
    const addTitle = t(kind === "owned" ? "collection_add_game_owned" : "collection_add_game_wish");
    document.getElementById("add-game-title").textContent = addTitle;
    document.getElementById("open-add").textContent = addTitle;
    document.getElementById("open-steam").classList.toggle("d-none", kind !== "owned");
    document.getElementById("open-psn").classList.toggle("d-none", kind !== "owned");
    sortOptions();
    const words = document.getElementById("filter-text").value.toLowerCase().split(/\s+/).filter(Boolean);
    const listed = data.items.filter(i => i.kind === kind
        && words.every(w => `${i.name || ""} ${i.name_en || ""}`.toLowerCase().includes(w)));
    const groups = filterGroups(listed);
    const sidebar = document.getElementById("filters");
    renderFilters(sidebar, listed, groups, chosen[kind], renderItems);
    filtersToggle(document.getElementById("filters-toggle"), sidebar, chosen[kind]);
    const items = filterItems(listed, groups, chosen[kind]).sort((a, b) => ORDER[sortBy[kind]](a, b) || byName(a, b));
    const list = document.getElementById("items");
    list.innerHTML = items.map(itemRow).join("");
    const empty = document.getElementById("empty");
    empty.textContent = data.items.some(i => i.kind === kind) ? t("no_results") : t(`collection_empty_${kind}`);
    empty.classList.toggle("d-none", items.length > 0);

    list.querySelectorAll("[data-id]").forEach(row => {
        const id = row.dataset.id;
        const editButton = row.querySelector("[data-action=edit]");
        if (editButton) editButton.onclick = () => openEditor(id);
        row.querySelector("[data-action=remove]").onclick = () => removeItem(data.items.find(i => String(i.id) === id));
        const bought = row.querySelector("[data-action=bought]");
        if (bought) bought.onclick = async () => {
            const { ok } = await api(`/api/collection/${id}`, { method: "PATCH", body: { kind: "owned" } });
            if (ok) { showMessage(true, t("collection_moved_owned")); load(); }
        };
    });
}

// Take an item out (the card's ✕, the window's "Tirar da coleção"); an imported one isn't imported again
async function removeItem(item) {
    const fromSteam = item.kind === "owned" && item.steam_app_id;
    const fromPsn = item.kind === "owned" && item.psn_id;
    if (!confirm(t(fromPsn ? "collection_remove_confirm_psn" : fromSteam ? "collection_remove_confirm_steam" : "collection_remove_confirm"))) return false;
    const { ok } = await api(`/api/collection/${item.id}`, { method: "DELETE" });
    if (ok) await load();
    return ok;
}

// An owned game's details in a window over the grid (user, 2026-10-11: not inside the card); each
// change is saved at once and says so, the grid is drawn again on closing
const dialog = document.getElementById("item-dialog");
let editing = null;          // the id of the item in the window
let reloadOnClose = false;   // its edition changed: its name and prices are the new edition's
function openEditor(id) {
    const item = data.items.find(i => String(i.id) === id);
    editing = id;
    const body = document.getElementById("item-dialog-body");
    body.innerHTML = `
        <div class="d-flex gap-3 align-items-start">
            <img class="dialog-cover" src="${esc(item.image || "")}" alt="">
            <div class="flex-grow-1 min-w-0">
                <h2 id="item-dialog-title" class="h5 mb-0">${esc(localName(item) || "")}</h2>
                <div class="small text-body-secondary">${esc(item.platform_name || "")}</div>
                <button type="button" class="btn btn-link btn-sm p-0 text-start" data-edition-toggle aria-expanded="false" aria-controls="edition-change">
                    ${esc(t("collection_edition"))}: <span data-edition-name>…</span> · ${esc(t("collection_edition_change_link"))}</button>
            </div>
            <button type="button" class="btn-close" data-close aria-label="${esc(t("collection_edit_done"))}"></button>
        </div>
        <form id="edition-change" class="row g-2 mt-1 d-none" novalidate>
            <div class="col-12"><label class="form-label small text-body-secondary mb-0 d-block">${esc(t("collection_edition"))}
                <select class="form-select form-select-sm" name="edition" disabled><option>…</option></select></label></div>
            <div class="col-12 d-none" data-typed>
                <div class="input-group input-group-sm">
                    <input name="typed" class="form-control" maxlength="100" placeholder="${esc(t("collection_other_edition_placeholder"))}"
                           aria-label="${esc(t("collection_other_edition"))}">
                    <button type="submit" class="btn btn-secondary">${t("collection_edition_change")}</button>
                </div>
            </div>
        </form>
        <p class="small text-body-secondary mt-2 mb-0">${esc(t("collection_saved_automatically"))}</p>
        ${ownedControls(item)}
        <div class="d-flex align-items-center gap-2 border-top pt-2 mt-3">
            <button type="button" class="btn btn-link btn-sm text-danger px-0" data-remove>${esc(t("collection_remove_from"))}</button>
            <span class="small text-success ms-auto" data-saved role="status"></span>
            <button type="button" class="btn btn-primary btn-sm" data-close>${t("collection_done")}</button>
        </div>`;
    const saved = body.querySelector("[data-saved]");
    const done = ok => {                       // "✓ Guardado" for a moment, or what went wrong
        saved.className = `small ms-auto ${ok === true ? "text-success" : "text-danger"}`;
        saved.textContent = ok === true ? t("collection_saved") : ok;
        clearTimeout(done.timer);
        if (ok === true) done.timer = setTimeout(() => saved.textContent = "", 2500);
    };
    const save = async (field, value) => {
        const { ok, data: answer } = await api(`/api/collection/${id}`, { method: "PATCH", body: { [field]: value } });
        if (!ok) { done(t(`error_${answer?.error || "unknown"}`)); return false; }
        const numeric = ["hours", "achievements", "achievements_total"].includes(field);
        item[field] = typeof value === "boolean" ? value : numeric ? (value ? Number(String(value).replace(",", ".")) : null) : value || null;
        data.stats = recount();
        renderStats();
        done(true);
        return true;
    };
    const press = (button, on) => {           // a pressed button in its colour (a status: its badge's)
        button.setAttribute("aria-pressed", on);
        button.classList.toggle(button.dataset.on, on);
    };
    body.querySelectorAll("[data-choice] , [data-toggle]").forEach(b => press(b, b.getAttribute("aria-pressed") === "true"));
    body.querySelectorAll("[data-choice]").forEach(button => button.onclick = async () => {
        const field = button.dataset.choice, group = body.querySelectorAll(`[data-choice="${field}"]`);
        const before = [...group].find(b => b.getAttribute("aria-pressed") === "true");
        group.forEach(b => press(b, b === button));
        const ok = field === "score" ? await saveScore(button.dataset.value) : await save(field, button.dataset.value);
        if (!ok) group.forEach(b => press(b, b === before));
    });
    body.querySelectorAll("[data-toggle]").forEach(button => button.onclick = async () => {
        const on = button.getAttribute("aria-pressed") !== "true";
        press(button, on);
        if (!await save(button.dataset.toggle, on)) press(button, !on);
    });
    body.querySelectorAll("[data-field]").forEach(input => input.onchange = async () => {
        if (await save(input.dataset.field, input.value) && input.dataset.field.startsWith("achievements"))
            body.querySelector("[data-progress]").innerHTML = progressBar(item);
    });
    // the score is the user's review of the game (game page): one per game, kept in step on every item of it
    const saveScore = async value => {
        if (item.score_locked) return false;
        const { ok, data: answer } = await api(`/api/games/${item.game_id}/reviews/mine/score`, { method: "PUT", body: { score: value } });
        if (!ok) { done(t(`error_${answer?.error || "unknown"}`)); return false; }
        data.items.filter(i => i.game_id === item.game_id).forEach(i => i.score = answer.score);
        done(true);
        return true;
    };
    if (item.score_locked) body.querySelectorAll('[data-choice="score"]').forEach(b => b.disabled = true);
    const editionForm = body.querySelector("#edition-change"), toggle = body.querySelector("[data-edition-toggle]");
    toggle.onclick = () => toggle.setAttribute("aria-expanded", !editionForm.classList.toggle("d-none"));
    body.querySelector("[data-remove]").onclick = async () => { if (await removeItem(item)) dialog.close(); };
    body.querySelectorAll("[data-close]").forEach(b => b.onclick = () => dialog.close());
    dialog.showModal();
    loadEditionChange(item);
}

// The item's edition in the edit window: one we know is saved when picked, a named one with "Mudar"
async function loadEditionChange(item) {
    const form = document.getElementById("edition-change");
    const choices = await editionChoices(item.game_id);
    const current = `id:${item.edition_id}`;
    form.edition.innerHTML = [...choices, { value: "other", label: t("collection_other_edition") }].map(c =>
        `<option value="${esc(c.value)}" ${c.value === current ? "selected" : ""}>${esc(c.label)}</option>`).join("");
    form.edition.disabled = false;
    const name = document.querySelector("[data-edition-name]");
    if (name) name.textContent = choices.find(c => c.value === current)?.label || t("collection_other_edition");
    const save = async () => {
        const { ok, data: answer } = await api(`/api/collection/${item.id}`, { method: "PATCH", body: editionBody(form.edition.value, form.typed.value) });
        if (!ok) return showMessage(false, t(`error_${answer?.error || "unknown"}`));
        reloadOnClose = true;
        showMessage(true, t("collection_edition_saved"));
    };
    form.edition.onchange = () => {
        const other = form.edition.value === "other";
        form.querySelector("[data-typed]").classList.toggle("d-none", !other);
        other ? form.typed.focus() : save();
    };
    form.onsubmit = event => { event.preventDefault(); save(); };
}
dialog.onclick = event => { if (event.target === dialog) dialog.close(); };      // a click outside the window

// "Adicionar um jogo" and the imports open their windows; ✕ or a click outside closes them
for (const [button, box] of [["open-add", "add-dialog"], ["open-steam", "steam-dialog"], ["open-psn", "psn-dialog"]]) {
    const window_ = document.getElementById(box);
    document.getElementById(button).onclick = () => window_.showModal();
    window_.onclick = event => { if (event.target === window_) window_.close(); };
    window_.querySelectorAll("[data-close]").forEach(b => b.onclick = () => window_.close());
}
dialog.onclose = async () => {
    if (reloadOnClose) {
        reloadOnClose = false;
        await load();
    }
    renderItems();
    document.querySelector(`#items [data-id="${editing}"] [data-action=edit]`)?.focus();
};

// The statistics again after an edit in the page (the server counts them the same way)
function recount() {
    const owned = data.items.filter(i => i.kind === "owned");
    const statuses = {};
    owned.forEach(i => { if (i.status) statuses[i.status] = (statuses[i.status] || 0) + 1; });
    const withTotal = owned.filter(i => i.achievements_total);
    return { ...data.stats, statuses, hours: owned.reduce((sum, i) => sum + (i.hours || 0), 0),
             completed: owned.filter(i => i.status === "finished").length,
             achievements: withTotal.reduce((sum, i) => sum + (i.achievements || 0), 0),
             achievements_total: withTotal.reduce((sum, i) => sum + i.achievements_total, 0) };
}

function renderPublicLink() {
    const box = document.getElementById("public-link");
    box.classList.toggle("d-none", !data.public);
    box.innerHTML = data.public ? `${esc(t("collection_public_at"))} <a href="/user/${encodeURIComponent(currentUser.username)}">/user/${esc(currentUser.username)}</a>` : "";
}

async function load() {
    const response = await fetch("/api/collection");
    document.getElementById("loading").classList.add("d-none");
    if (!response.ok) return showMessage(false, t("error_unknown"));
    data = await response.json();
    document.getElementById("public-switch").checked = data.public;
    document.getElementById("alerts-switch").checked = data.wish_alerts;
    renderPublicLink();
    renderStats();
    renderItems();
    document.getElementById("content").classList.remove("d-none");
}

// A game not in the collection yet, from the catalogue or (one no store sells) IGDB (user, 2026-10-07):
// its Standard edition goes onto the open tab; a game IGDB has and we don't is created first
// Which edition (user, 2026-10-11: a "Lumière Edition" that neither the stores nor IGDB list): the
// game's editions, IGDB's we don't have, or one the user names. Used to add a game and to change one
async function editionChoices(gameId) {
    const [ours, igdb] = await Promise.all([
        fetch(`/api/games/${gameId}/editions`).then(r => r.ok ? r.json() : []).catch(() => []),
        fetch(`/api/igdb/games/${gameId}/editions`).then(r => r.ok ? r.json() : []).catch(() => []),   // IGDB down: ours only
    ]);
    return [...ours.map(e => ({ value: `id:${e.id}`, label: localName(e) })),
            ...igdb.map(name => ({ value: `new:${name}`, label: name }))];
}

// What to send for a choice: {edition_id} or {new_edition}
function editionBody(value, typed) {
    if (value === "other") return { new_edition: typed.trim() };
    return value.startsWith("id:") ? { edition_id: Number(value.slice(3)) } : { new_edition: value.slice(4) };
}

async function addGame(gameId, editionId) {
    const form = document.getElementById("add-step-edition");
    const [choices, game] = await Promise.all([editionChoices(gameId),
                                               fetch(`/api/games/${gameId}`).then(r => r.ok ? r.json() : null).catch(() => null)]);
    const chosen = editionId ? `id:${editionId}` : choices[0]?.value || "other";
    form.innerHTML = `
        ${game ? `<p class="mb-2"><strong>${esc(localName(game, "title"))}</strong> <span class="text-body-secondary small">${esc(game.platform_name)}</span></p>` : ""}
        <fieldset>
            <legend class="h6">${t(kind === "owned" ? "collection_which_edition_owned" : "collection_which_edition_wish")}</legend>
            ${[...choices, { value: "other", label: t("collection_other_edition") }].map((c, i) => `
                <div class="form-check">
                    <input class="form-check-input" type="radio" name="edition" id="edition-${i}" value="${esc(c.value)}" ${c.value === chosen ? "checked" : ""}>
                    <label class="form-check-label" for="edition-${i}">${esc(c.label)}</label>
                </div>`).join("")}
            <input name="typed" class="form-control form-control-sm mt-1" maxlength="100" ${chosen === "other" ? "" : "disabled"}
                   placeholder="${esc(t("collection_other_edition_placeholder"))}" aria-label="${esc(t("collection_other_edition"))}">
        </fieldset>
        ${kind === "owned" ? `
        <fieldset class="mt-3">
            <legend class="h6">${t("collection_format")}</legend>
            ${["physical", "digital"].map(x => `
                <div class="form-check form-check-inline">
                    <input class="form-check-input" type="radio" name="format" id="format-${x}" value="${x}" ${x === "physical" ? "checked" : ""}>
                    <label class="form-check-label" for="format-${x}">${t(`format_${x}`)}</label>
                </div>`).join("")}
        </fieldset>` : ""}
        <div class="d-flex gap-2 justify-content-end mt-3">
            <button type="button" class="btn btn-sm btn-secondary" data-back>${t("collection_back")}</button>
            <button type="submit" class="btn btn-sm btn-primary">${t("collection_add_this")}</button>
        </div>`;
    form.querySelectorAll("[name=edition]").forEach(r => r.onchange = () => {
        form.typed.disabled = form.edition.value !== "other";
        if (!form.typed.disabled) form.typed.focus();
    });
    form.querySelector("[data-back]").onclick = () => showAddStep("game");
    form.onsubmit = async event => {
        event.preventDefault();
        const { ok, data: answer } = await api("/api/collection", { body: { kind, game_id: gameId, ...editionBody(form.edition.value, form.typed.value),
                                                                    ...(kind === "owned" ? { format: form.format.value } : {}) } });
        if (!ok) return showMessage(false, t(`error_${answer?.error || "unknown"}`));
        document.getElementById("add-dialog").close();
        await load();
        showMessage(true, t(kind === "owned" ? "collection_added_owned" : "collection_added_wish"));
    };
    showAddStep("edition");
}

function showAddStep(step) {
    document.getElementById("add-step-game").classList.toggle("d-none", step !== "game");
    document.getElementById("add-step-edition").classList.toggle("d-none", step !== "edition");
    if (step === "game") clearAddSearch();
}
document.getElementById("add-dialog").addEventListener("close", () => showAddStep("game"));

const clearAddSearch = gamePicker({
    search: document.getElementById("add-search"),
    results: document.getElementById("add-results"),
    igdbButton: document.getElementById("add-igdb"),
    igdbResults: document.getElementById("add-igdb-results"),
}, addGame, code => showMessage(false, t(`error_${code}`)));

// The user's Steam games (steam_service) or PlayStation games (psn_service): all go in at once, with
// hours and achievements / trophies (the ones no store sells only in the collection); those IGDB doesn't
// know are listed. No profile: the last one again. key: steam | psn, the elements' and texts' prefix;
// field: what the API calls the profile; options: more of the request's body (PSN: the PS Plus games too?)
function importer(key, field, options = () => ({})) {
    const element = id => document.getElementById(`${key}-${id}`);
    async function run(profile) {
        const result = element("result"), list = element("missing");
        const buttons = document.querySelectorAll(`#${key}-form button, #${key}-refresh`);
        buttons.forEach(b => b.disabled = true);
        result.textContent = t("steam_importing");
        list.innerHTML = "";
        const { ok, data: answer } = await api(`/api/collection/${key}`, { body: { ...options(), ...(profile ? { [field]: profile } : {}) } });
        buttons.forEach(b => b.disabled = false);
        if (!ok) return result.textContent = t(`error_${answer?.error || "unknown"}`);
        result.textContent = t(`${key}_imported`, { total: answer.total, added: answer.added, updated: answer.updated })
            + (answer.skipped ? " " + t("steam_skipped", { n: answer.skipped }) : "")
            + (answer.ps_plus ? " " + t("psn_plus_left_out", { n: answer.ps_plus }) : "")
            + (answer.missing.length ? " " + t("steam_missing", { missing: answer.missing.length }) : "");
        const detail = m => m.hours ? ` · ${fmtNumber(m.hours)} h` : m.platform ? ` · ${esc(m.platform)}` : "";
        list.innerHTML = answer.missing.map(m => `
            <div class="list-group-item py-1 small">${esc(m.name)}<span class="text-body-secondary">${detail(m)}</span></div>`).join("");
        if (answer.added || answer.updated) load();
        loadProfile();
    }
    async function loadProfile() {
        const response = await fetch(`/api/collection/${key}`);
        const data = response.ok ? await response.json() : null;
        const saved = data?.profile;
        element("saved").classList.toggle("d-none", !saved);
        if (!saved) return;
        element("last").textContent = (saved.online_id ? saved.online_id + " · " : "") + (saved.imported_at
            ? t("steam_last_import", { date: new Date(saved.imported_at).toLocaleString(LOCALE, { dateStyle: "short", timeStyle: "short" }) })
            : "");
    }
    element("form").onsubmit = event => {
        event.preventDefault();
        run(element("profile").value);
    };
    element("refresh").onclick = () => run(null);
    loadProfile();
}
importer("steam", "profile");
importer("psn", "name", () => ({ ps_plus: document.getElementById("psn-plus").checked }));

// The link in a wishlist alert e-mail (?alerts_off=…) works without logging in
async function alertsOffFromLink() {
    const token = new URLSearchParams(location.search).get("alerts_off");
    if (!token) return false;
    history.replaceState(null, "", location.pathname);
    const { ok, data: answer } = await api("/api/collection/alerts-off", { body: { token } });
    showMessage(ok, ok ? t("collection_alerts_off_done") : t(`error_${answer?.error || "unknown"}`));
    return true;
}

async function start() {
    applyI18n();
    const fromLink = await alertsOffFromLink();
    await renderAccountArea();
    if (!currentUser && fromLink) return document.getElementById("loading").classList.add("d-none");
    if (!currentUser) return location.replace(`/account?next=${encodeURIComponent(location.pathname + location.search)}`);
    document.getElementById("sort").onchange = event => { sortBy[kind] = event.target.value; renderItems(); };
    document.getElementById("filter-text").oninput = renderItems;
    document.querySelectorAll("[data-kind]").forEach(b => b.onclick = () => {
        kind = b.dataset.kind;
        history.replaceState(null, "", kind === "wishlist" ? "?tab=wishlist" : location.pathname);
        renderItems();
    });
    document.getElementById("public-switch").onchange = async e => {
        const { ok } = await api("/api/collection/settings", { method: "PUT", body: { public: e.target.checked } });
        if (ok) { data.public = e.target.checked; renderPublicLink(); }
    };
    document.getElementById("alerts-switch").onchange = async e => {
        const { ok } = await api("/api/collection/settings", { method: "PUT",
                                                               body: { wish_alerts: e.target.checked, lang: LANG } });
        if (ok) data.wish_alerts = e.target.checked;
        else e.target.checked = !e.target.checked;
    };
    load();
}
start();
