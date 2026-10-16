// The profile page (templates/profile.html). A file, not inline: the site's CSP only runs scripts from files.
const USERNAME = document.body.dataset.username;
let USER_ID = null;

function stars(n) {
    return `<span class="text-warning" aria-label="${esc(t("stars_n", { n }))}">${"★".repeat(n)}${"☆".repeat(5 - n)}</span>`;
}

// The services' own names: the same in both languages
const SERVICES = { psn: "PSN", xbox: "Xbox", steam: "Steam", nintendo: "Nintendo Switch", epic: "Epic Games",
                   youtube: "YouTube", twitch: "Twitch" };

// The gamer names and channels (gaming_accounts.shown): a link to the service's page where it has one
function showAccounts(accounts) {
    const box = document.getElementById("gaming-accounts");
    box.innerHTML = accounts.map(a => {
        const text = `<strong>${esc(SERVICES[a.kind])}</strong>${a.name ? ` ${esc(a.name)}` : ""}`;
        return a.url
            ? `<a role="listitem" class="badge rounded-pill bg-body-secondary text-body border text-decoration-none fw-normal"
                  href="${esc(a.url)}" target="_blank" rel="noopener noreferrer nofollow ugc">${text} ↗</a>`
            : `<span role="listitem" class="badge rounded-pill bg-body-secondary text-body border fw-normal user-select-all">${text}</span>`;
    }).join("");
    box.classList.toggle("d-none", !accounts.length);
}

async function load() {
    await renderAccountArea();
    const response = await fetch(`/api/users/${encodeURIComponent(USERNAME)}`);
    document.getElementById("loading").classList.add("d-none");
    if (!response.ok) return document.getElementById("error").classList.remove("d-none");
    const user = await response.json();
    USER_ID = user.id;
    document.title = `@${user.username} · SaveOnGames`;
    document.getElementById("name").textContent =
        user.display_name !== user.username ? `${user.display_name} (@${user.username})` : `@${user.username}`;
    document.getElementById("since").textContent =
        `${t("member_since")} ${new Date(user.created_at).toLocaleDateString(LOCALE)}`;
    document.getElementById("average").innerHTML = user.rating_count ? `★ ${fmtNumber(user.rating)}` : "—";
    document.getElementById("count").textContent = t("profile_rating_count", { count: user.rating_count });

    document.getElementById("avatar").innerHTML = avatarImage(user.avatar, 72);
    const where = document.getElementById("location");
    where.innerHTML = user.location ? `${icon("pin", 16)} ${esc(user.location)}` : "";
    where.classList.toggle("d-none", !user.location);
    showAccounts(user.accounts);
    const mine = currentUser && currentUser.id === user.id;     // the person can answer their ratings
    document.getElementById("edit-profile").classList.toggle("d-none", !mine);
    document.getElementById("report-user").innerHTML = mine ? "" : reportButton("user", user.id);
    const list = document.getElementById("ratings");
    list.innerHTML = user.ratings.map(r => `
        <div class="list-group-item">
            <div class="d-flex justify-content-between flex-wrap gap-1">
                <span>${stars(r.stars)} <span class="small text-body-secondary">
                    ${esc(t(r.rated_as === "seller" ? "rated_as_seller" : "rated_as_buyer", { user: userLabel(r.rater_username), game: r.title }))}</span></span>
                <span class="small text-body-secondary">${new Date(r.created_at).toLocaleDateString(LOCALE)}
                    ${currentUser?.username !== r.rater_username ? `·${reportButton("rating", r.id)}` : ""}</span>
            </div>
            ${r.comment ? `<div class="mt-1">${esc(r.comment)}</div>` : ""}
            ${r.reply ? `<div class="mt-1 ms-3 small border-start ps-2"><strong>${esc(t("reply_from", { user: userLabel(user.username) }))}</strong> ${esc(r.reply)}</div>` : ""}
            ${mine ? `<form class="reply-form d-flex gap-1 mt-2" data-id="${r.id}">
                <input name="reply" maxlength="500" class="form-control form-control-sm" value="${esc(r.reply || "")}"
                       placeholder="${esc(t("reply_placeholder"))}" aria-label="${esc(t("reply_placeholder"))}">
                <button class="btn btn-sm btn-secondary">${t("reply_save")}</button></form>` : ""}
        </div>`).join("");
    list.querySelectorAll(".reply-form").forEach(form => form.onsubmit = async e => {
        e.preventDefault();
        const { ok } = await api(`/api/ratings/${form.dataset.id}/reply`, { body: { reply: form.reply.value } });
        if (ok) load();
    });
    document.getElementById("no-ratings").classList.toggle("d-none", user.ratings.length > 0);

    document.getElementById("listings").innerHTML = user.listings.map(l => listingCard(l, { showSeller: false })).join("");
    document.getElementById("no-listings").classList.toggle("d-none", user.listings.length > 0);
    showGameReviews(user.game_reviews);
    document.getElementById("profile").classList.remove("d-none");
    loadCollection();
    loadFollows(mine);
}

// Following (follow_service): the counts, follow / unfollow, and on the user's own profile who they follow
async function loadFollows(mine) {
    const counts = await fetch(`/api/users/${encodeURIComponent(USERNAME)}/follows`).then(r => r.ok ? r.json() : null);
    if (!counts) return;
    document.getElementById("follow-counts").textContent =
        t("follow_counts", { followers: counts.followers, following: counts.following });
    const button = document.getElementById("follow-button");
    button.classList.toggle("d-none", mine);
    button.textContent = t(counts.followed ? "unfollow" : "follow");
    button.classList.toggle("btn-primary", !counts.followed);
    button.classList.toggle("btn-secondary", counts.followed);
    button.setAttribute("aria-pressed", counts.followed);
    button.onclick = async () => {
        if (!currentUser) return location.assign(`/account?next=${encodeURIComponent(location.pathname)}`);
        const { ok } = await api(`/api/users/${encodeURIComponent(USERNAME)}/follow`,
                                 { method: counts.followed ? "DELETE" : "POST" });
        if (ok) loadFollows(mine);
    };
    if (mine) loadFollowing();
}

async function loadFollowing() {
    const people = await fetch("/api/following").then(r => r.ok ? r.json() : []);
    document.getElementById("following-list").innerHTML = people.map(p => `
        <div class="list-group-item d-flex flex-wrap align-items-center gap-2">
            ${avatarImage(p.avatar, 32)}
            <a href="/user/${encodeURIComponent(p.username)}" class="me-auto">${esc(userLabel(p.username))}</a>
            ${p.collection_public ? `<a href="/compare/${encodeURIComponent(p.username)}" class="btn btn-sm btn-secondary">${t("compare_collections")}</a>`
                                  : `<span class="small text-body-secondary">${t("compare_private")}</span>`}
        </div>`).join("");
    document.getElementById("following-none").classList.toggle("d-none", people.length > 0);
    document.getElementById("following").classList.remove("d-none");
}

// Long texts are cut here; the whole review is on the game's page
function showGameReviews(reviews) {
    const cut = text => text.length > 300 ? `${text.slice(0, 300).trimEnd()}…` : text;
    const style = score => score >= 8 ? "text-bg-success" : score >= 5 ? "text-bg-warning" : "text-bg-danger";
    document.getElementById("game-reviews-list").innerHTML = reviews.map(r => `
        <div class="list-group-item">
            <div class="d-flex justify-content-between flex-wrap gap-1">
                <span><span class="badge ${style(r.score)}">${r.score}/10</span>
                    <a href="/game/${r.game_id}" class="fw-semibold">${esc(r.game)}</a>
                    <span class="small text-body-secondary">${esc(r.platform_name)}</span></span>
                <span class="small text-body-secondary">${new Date(r.created_at).toLocaleDateString(LOCALE)}
                    ${currentUser?.id !== USER_ID ? `· ${reportButton("review", r.id)}` : ""}</span>
            </div>
            ${r.title ? `<div class="fw-semibold mt-1">${esc(r.title)}</div>` : ""}
            ${r.body ? `<div class="small mt-1" style="white-space: pre-line;">${esc(cut(r.body))}</div>` : ""}
        </div>`).join("");
    document.getElementById("game-reviews").classList.toggle("d-none", !reviews.length);
}

// The user's collection, if they made it public (app/services/collection_service.py)
async function loadCollection() {
    const response = await fetch(`/api/users/${encodeURIComponent(USERNAME)}/collection`);
    if (currentUser && currentUser.id === USER_ID) loadShowcaseEditor(response.ok);
    if (!response.ok) return;
    if (currentUser && currentUser.id !== USER_ID) {        // public: the visitor can compare theirs with it
        const link = document.getElementById("compare-link");
        link.href = `/compare/${encodeURIComponent(USERNAME)}`;
        link.classList.remove("d-none");
    }
    const { stats, showcase } = await response.json();
    showShowcase(showcase);
    document.getElementById("collection-summary").textContent =
        t("profile_collection_summary", { owned: stats.owned, completed: stats.completed, wishlist: stats.wishlist });
    document.getElementById("see-collection").href = `/user/${encodeURIComponent(USERNAME)}/collection`;
    document.getElementById("collection").classList.remove("d-none");
}

// --- the showcase ---------------------------------------------------------------------------
const SECTIONS = ["favourites", "most_played", "most_valuable", "achievements"];
const MAX_FAVOURITES = 10;

function showShowcase(sections) {
    // HTML (the trophies line has an icon)
    const caption = (section, g, i) => ({
        favourites: `#${i + 1}`,
        most_played: esc(`${fmtNumber(g.hours)} h`),
        most_valuable: g.value != null ? esc(eur.format(g.value)) : "",
        achievements: `${icon("trophy", 13)} ${esc(`${g.achievements}/${g.achievements_total}`)}`,
    })[section];
    document.getElementById("showcase").innerHTML = sections.map(s => `
        <section class="mb-4">
            <h2 class="h5">${esc(t(`showcase_${s.section}`))}</h2>
            <div class="row row-cols-3 row-cols-sm-5 g-2">${s.items.map((g, i) => `
                <div class="col"><a href="/game/${g.game_id}" class="d-block text-decoration-none text-body small">
                    ${g.image ? `<img src="${esc(g.image)}" alt="" class="w-100 rounded mb-1 object-fit-cover ${coverClass(g.image)}" style="aspect-ratio: 3 / 4;">`
                              : `<div class="w-100 rounded mb-1 bg-body-secondary" style="aspect-ratio: 3 / 4;"></div>`}
                    <div class="text-truncate fw-semibold">${esc(localName(g) || "")}</div>
                    <div class="text-body-secondary text-truncate">${caption(s.section, g, i)} · ${esc(g.platform_name || "")}</div>
                </a></div>`).join("")}
            </div>
        </section>`).join("");
}

// The user's own profile: which sections, in what order, and the top 10 (from their owned games), in a window
// (user, 2026-10-16): the top 10 as covers, games added by searching the collection, both lists in order by
// dragging their handle (or with the arrow buttons: keyboards, small screens). Nothing is kept until "Guardar"
let savedShowcase = null;          // {order: [{section, shown}], favourites: [item]} as last saved
let editor = null;          // the same, being changed, and owned: [item]
const dialog = document.getElementById("showcase-editor");

async function loadShowcaseEditor(isPublic) {
    const response = await fetch("/api/collection");
    if (!response.ok) return;
    const data = await response.json();
    const owned = data.items.filter(i => i.kind === "owned")
        .sort((a, b) => (localName(a) || "").localeCompare(localName(b) || "", LOCALE));
    savedShowcase = {
        order: [...data.profile_sections.map(s => ({ section: s, shown: true })),
                ...SECTIONS.filter(s => !data.profile_sections.includes(s)).map(s => ({ section: s, shown: false }))],
        favourites: owned.filter(i => i.favourite_rank).sort((a, b) => a.favourite_rank - b.favourite_rank),
        owned,
    };
    document.getElementById("showcase-private").classList.toggle("d-none", isPublic);
    const toggle = document.getElementById("showcase-toggle");
    toggle.classList.remove("d-none");
    toggle.onclick = openEditor;
}

function openEditor() {
    editor = { order: savedShowcase.order.map(o => ({ ...o })), favourites: [...savedShowcase.favourites], owned: savedShowcase.owned };
    document.getElementById("showcase-saved").textContent = "";
    document.getElementById("showcase-search").value = "";
    renderEditor();
    dialog.showModal();
}

dialog.querySelector(".input-group-text").innerHTML = icon("search", 14);
dialog.querySelectorAll("[data-close]").forEach(b => b.onclick = () => dialog.close());
dialog.onclick = event => { if (event.target === dialog) dialog.close(); };          // a click outside the window
dialog.onclose = () => document.getElementById("showcase-toggle").focus();

function move(list, from, to) {
    if (to < 0 || to >= list.length || from === to) return;
    list.splice(to, 0, list.splice(from, 1)[0]);
    renderEditor();
}

function arrowButton(kind, i, step, name, label, disabled) {
    return `<button type="button" class="btn btn-sm btn-secondary icon-btn" data-${kind}-move="${i}" data-step="${step}"
                    aria-label="${esc(label)}" title="${esc(label)}" ${disabled ? "disabled" : ""}>${icon(name, 14)}</button>`;
}

function renderEditor() {
    const sections = document.getElementById("showcase-section-list");
    const lastSection = editor.order.length - 1;
    sections.innerHTML = editor.order.map((o, i) => `
        <li class="sort-row" data-index="${i}">
            <button type="button" class="drag-handle" tabindex="-1" aria-hidden="true">${icon("grip", 16)}</button>
            <label class="form-check-label d-flex align-items-center gap-2 flex-grow-1 min-w-0">
                <input type="checkbox" class="form-check-input mt-0" data-shown="${i}" ${o.shown ? "checked" : ""}>
                ${esc(t(`showcase_${o.section}`))}</label>
            ${arrowButton("section", i, -1, "up", t("showcase_up"), i === 0)}
            ${arrowButton("section", i, 1, "down", t("showcase_down"), i === lastSection)}
        </li>`).join("");
    sections.querySelectorAll("[data-shown]").forEach(b => b.onchange = () => editor.order[b.dataset.shown].shown = b.checked);
    sections.querySelectorAll("[data-section-move]").forEach(b => b.onclick = () =>
        move(editor.order, +b.dataset.sectionMove, +b.dataset.sectionMove + +b.dataset.step));
    sortable(sections, editor.order);

    const favourites = document.getElementById("showcase-favourite-list");
    const lastFavourite = editor.favourites.length - 1;
    favourites.innerHTML = editor.favourites.map((f, i) => `
        <li class="fav-tile" data-index="${i}">
            ${f.image ? `<img src="${esc(f.image)}" alt="" class="${coverClass(f.image)}" loading="lazy">` : `<div class="fav-none"></div>`}
            <span class="badge text-bg-dark fav-rank">#${i + 1}</span>
            <button type="button" class="btn btn-sm btn-danger icon-btn fav-remove" data-remove="${i}"
                    aria-label="${esc(t("showcase_remove_game", { game: localName(f) || "" }))}" title="${esc(t("showcase_remove"))}">${icon("x", 14)}</button>
            <button type="button" class="drag-handle" tabindex="-1" aria-hidden="true">${icon("grip", 16)}</button>
            <div class="small fw-semibold text-truncate mt-1" title="${esc(localName(f) || "")}">${esc(localName(f) || "")}</div>
            <div class="d-flex align-items-center gap-1">
                <span class="small text-body-secondary text-truncate flex-grow-1">${esc(f.platform_name || "")}</span>
                ${arrowButton("favourite", i, -1, "left", t("showcase_earlier"), i === 0)}
                ${arrowButton("favourite", i, 1, "right", t("showcase_later"), i === lastFavourite)}
            </div>
        </li>`).join("") + (lastFavourite + 1 < MAX_FAVOURITES     // a free place: to the search
            ? `<li><button type="button" class="fav-empty w-100 bg-transparent" data-to-search
                           aria-label="${esc(t("showcase_add_label"))}">${icon("plus", 20)}</button></li>` : "");
    favourites.querySelector("[data-to-search]")?.addEventListener("click", () => document.getElementById("showcase-search").focus());
    favourites.querySelectorAll("[data-favourite-move]").forEach(b => b.onclick = () =>
        move(editor.favourites, +b.dataset.favouriteMove, +b.dataset.favouriteMove + +b.dataset.step));
    favourites.querySelectorAll("[data-remove]").forEach(b => b.onclick = () => { editor.favourites.splice(+b.dataset.remove, 1); renderEditor(); });
    sortable(favourites, editor.favourites);
    renderResults();
}

// Dragging by the handle (mouse, finger or pen): the item follows the pointer over the others; let go, and
// the list takes that order
function sortable(list, items) {
    // followed on the whole page: moving the item in the list would lose a pointer capture on its handle
    list.querySelectorAll(".drag-handle").forEach(handle => handle.onpointerdown = down => {
        if (down.button !== 0) return;
        down.preventDefault();               // no text selection while dragging
        const dragged = handle.closest("[data-index]");
        const from = +dragged.dataset.index;
        dragged.classList.add("dragging");
        const follow = event => {
            if (event.pointerId !== down.pointerId) return;
            const over = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-index]");
            if (!over || over === dragged || over.parentElement !== list) return;
            const box = over.getBoundingClientRect();
            const after = list.classList.contains("fav-grid") ? event.clientX > box.left + box.width / 2
                                                              : event.clientY > box.top + box.height / 2;
            list.insertBefore(dragged, after ? over.nextSibling : over);
        };
        const drop = event => {
            if (event.pointerId !== down.pointerId) return;
            document.removeEventListener("pointermove", follow);
            document.removeEventListener("pointerup", drop);
            document.removeEventListener("pointercancel", drop);
            const to = [...list.querySelectorAll("[data-index]")].indexOf(dragged);
            dragged.classList.remove("dragging");
            if (to !== from) move(items, from, to); else renderEditor();
        };
        document.addEventListener("pointermove", follow);
        document.addEventListener("pointerup", drop);
        document.addEventListener("pointercancel", drop);
    });
}

// The owned games matching the search (every word in the name), not in the top 10 yet
function renderResults() {
    const box = document.getElementById("showcase-results"), search = document.getElementById("showcase-search");
    const full = editor.favourites.length >= MAX_FAVOURITES;
    search.disabled = full;
    search.placeholder = t(full ? "showcase_full" : "showcase_search");
    const words = search.value.toLowerCase().split(/\s+/).filter(Boolean);
    const chosen = new Set(editor.favourites.map(f => f.id));
    const found = full || !words.length ? [] : editor.owned.filter(i => !chosen.has(i.id)
        && words.every(w => `${i.name || ""} ${i.name_en || ""}`.toLowerCase().includes(w))).slice(0, 8);
    box.innerHTML = found.map(i => `
        <button type="button" class="list-group-item list-group-item-action d-flex align-items-center gap-2 py-1" data-add="${i.id}">
            ${i.image ? `<img src="${esc(i.image)}" alt="" class="${coverClass(i.image)}" loading="lazy">` : ""}
            <span class="min-w-0 text-truncate">${esc(localName(i) || "")} <span class="small text-body-secondary">${esc(i.platform_name || "")}</span></span>
            <span class="ms-auto">${icon("plus", 16)}</span>
        </button>`).join("") + (words.length && !found.length && !full
            ? `<div class="small text-body-secondary px-1">${esc(t("no_results"))}</div>` : "");
    box.querySelectorAll("[data-add]").forEach(b => b.onclick = () => {
        const item = editor.owned.find(i => i.id === Number(b.dataset.add));
        if (item && editor.favourites.length < MAX_FAVOURITES) editor.favourites.push(item);
        search.value = "";
        renderEditor();
        search.disabled ? dialog.querySelector("#showcase-save").focus() : search.focus();
    });
}
document.getElementById("showcase-search").oninput = renderResults;

document.getElementById("showcase-save").onclick = async () => {
    const status = document.getElementById("showcase-saved");
    const { ok, data } = await api("/api/collection/showcase", { method: "PUT", body: {
        sections: editor.order.filter(o => o.shown).map(o => o.section),
        favourites: editor.favourites.map(f => f.id),
    } });
    status.className = `small me-auto ${ok ? "text-success" : "text-danger"}`;
    status.textContent = ok ? t("showcase_saved") : t(`error_${data?.error || "unknown"}`);
    if (!ok) return;
    savedShowcase = { ...savedShowcase, order: editor.order.map(o => ({ ...o })), favourites: [...editor.favourites] };
    loadCollection();
    setTimeout(() => dialog.close(), 600);
};

applyI18n();
load();
