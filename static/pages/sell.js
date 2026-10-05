// The sell page (templates/sell.html). A file, not inline: the site's CSP only runs scripts from files.
const MIN_PHOTOS = 3, MAX_PHOTOS = 10, MAX_BYTES = 10 * 1024 * 1024;
let game = null;          // {id, title, platform}
let photos = [];          // File objects, in the order they'll be shown

function showError(code, values) {
    const box = document.getElementById("sell-error");
    box.textContent = t(`error_${code}`, values);
    box.classList.remove("d-none");
}

// --- the game ----------------------------------------------------------------------------
let searchTimer;
document.getElementById("game-search").addEventListener("input", e => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => searchGames(e.target.value.trim()), 250);
});

async function searchGames(q) {
    const list = document.getElementById("game-results");
    document.getElementById("igdb-results").innerHTML = "";
    document.getElementById("igdb-search").classList.toggle("d-none", q.length < 2);
    if (q.length < 2) { list.innerHTML = ""; return; }
    const { games } = await fetch(`/api/games?q=${encodeURIComponent(q)}&per_page=8`).then(r => r.json());
    list.innerHTML = games.map(g => `
        <button type="button" class="list-group-item list-group-item-action d-flex align-items-center gap-2 game-option" data-id="${g.id}">
            <img src="${esc(g.image || "")}" alt="">
            <span>${esc(g.title)} <span class="text-body-secondary small">· ${esc(g.platform)}</span></span>
        </button>`).join("") || `<div class="list-group-item small text-body-secondary">${t("no_results")}</div>`;
    list.querySelectorAll("[data-id]").forEach(b => b.onclick = () => chooseGame(Number(b.dataset.id)));
}

// Games the catalogue doesn't have: IGDB's, each with a button per platform; picking one creates
// the game on that platform (app/services/igdb_game_service.py)
document.getElementById("igdb-search").onclick = async () => {
    const list = document.getElementById("igdb-results");
    list.innerHTML = `<div class="list-group-item small text-body-secondary">${t("sell_igdb_searching")}</div>`;
    const q = document.getElementById("game-search").value.trim();
    const response = await fetch(`/api/igdb/games?q=${encodeURIComponent(q)}`);
    const games = response.ok ? await response.json() : null;
    if (!games) {
        list.innerHTML = `<div class="list-group-item small text-danger">${t("error_igdb_unavailable")}</div>`;
        return;
    }
    list.innerHTML = games.map(g => `
        <div class="list-group-item d-flex align-items-center gap-2 game-option">
            <img src="${esc(g.cover || "")}" alt="">
            <div class="min-w-0">
                <div>${esc(g.name)}${g.year ? ` <span class="text-body-secondary small">(${g.year})</span>` : ""}</div>
                <div class="d-flex flex-wrap gap-1 mt-1">${g.platforms.map(p => `
                    <button type="button" class="btn btn-sm btn-primary py-0" data-igdb="${g.igdb_id}" data-platform="${esc(p.code)}">
                        ${esc(p.name)}</button>`).join("")}</div>
            </div>
        </div>`).join("") || `<div class="list-group-item small text-body-secondary">${t("sell_igdb_empty")}</div>`;
    list.querySelectorAll("[data-igdb]").forEach(b => b.onclick = async () => {
        b.disabled = true;
        const { ok, data } = await api("/api/igdb/games", { body: { igdb_id: Number(b.dataset.igdb), platform: b.dataset.platform } });
        b.disabled = false;
        if (!ok) return showError(data?.error || "unknown");
        list.innerHTML = "";
        chooseGame(data.game_id, data.edition_id);
    });
};

async function chooseGame(id, editionId = null) {
    const data = await fetch(`/api/games/${id}`).then(r => r.ok ? r.json() : null);
    if (!data) return;
    game = data;
    document.getElementById("chosen-game").innerHTML = `
        <strong>${esc(data.title)}</strong><span class="badge text-bg-secondary">${esc(data.platform_name)}</span>
        <button type="button" class="btn btn-sm btn-secondary ms-auto" id="change-game">${t("sell_change_game")}</button>`;
    document.getElementById("chosen-game").classList.remove("d-none");
    document.getElementById("game-picker").classList.add("d-none");
    document.getElementById("change-game").onclick = () => {
        game = null;
        document.getElementById("chosen-game").classList.add("d-none");
        document.getElementById("game-picker").classList.remove("d-none");
        document.getElementById("edition").disabled = true;
    };

    const editions = document.getElementById("edition");
    editions.innerHTML = data.editions.map(e => `<option value="${e.id}">${esc(e.name)}</option>`).join("");
    editions.disabled = !data.editions.length;
    if (editionId && data.editions.some(e => e.id === editionId)) editions.value = editionId;   // "Vender" from the collection
    editions.onchange = storePriceHint;
    storePriceHint();
    addIgdbEditions(id);
}

// The game's other editions on IGDB (Collector's, Steelbook…): picked from IGDB's list, never typed,
// and created with the listing. Nothing is added when IGDB doesn't answer.
async function addIgdbEditions(gameId) {
    const names = await fetch(`/api/igdb/games/${gameId}/editions`).then(r => r.ok ? r.json() : []).catch(() => []);
    if (!names.length || game?.id !== gameId) return;
    const group = document.createElement("optgroup");
    group.label = t("sell_more_editions");
    for (const name of names) group.appendChild(new Option(name, `new:${name}`));
    const editions = document.getElementById("edition");
    editions.appendChild(group);
    editions.disabled = false;
}

// "New at the stores from €X": helps the seller choose a price
function storePriceHint() {
    const edition = game?.editions.find(e => String(e.id) === document.getElementById("edition").value);
    document.getElementById("store-price-hint").textContent = edition?.best_price
        ? t("sell_store_price", { price: eur.format(edition.best_price) }) : "";
}

// --- photos ------------------------------------------------------------------------------
document.getElementById("photos").addEventListener("change", e => {
    document.getElementById("sell-error").classList.add("d-none");
    for (const file of e.target.files) {
        if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) { showError("photo_type"); continue; }
        if (file.size > MAX_BYTES) { showError("photo_too_big"); continue; }
        if (photos.length >= MAX_PHOTOS) { showError("photo_count"); break; }
        photos.push(file);
    }
    e.target.value = "";      // the same file can be chosen again after removing it
    renderPreviews();
});

document.getElementById("add-photos").onclick = () => document.getElementById("photos").click();

function renderPreviews() {
    document.getElementById("photos-count").textContent = t("sell_photos_count", { count: photos.length, max: MAX_PHOTOS });
    const box = document.getElementById("previews");
    box.innerHTML = "";
    photos.forEach((file, i) => {
        const figure = document.createElement("figure");
        const url = URL.createObjectURL(file);
        figure.innerHTML = `<img src="${url}" alt="">
            <button type="button" class="btn btn-sm btn-danger" aria-label="${esc(t("remove_photo"))}">✕</button>
            ${i === 0 ? `<span class="badge text-bg-primary first">${t("sell_first_photo")}</span>` : ""}`;
        figure.querySelector("img").onload = () => URL.revokeObjectURL(url);
        figure.querySelector("button").onclick = () => { photos.splice(i, 1); renderPreviews(); };
        box.appendChild(figure);
    });
}

// --- publish -----------------------------------------------------------------------------
document.getElementById("sell-form").onsubmit = async event => {
    event.preventDefault();
    document.getElementById("sell-error").classList.add("d-none");
    if (!game) return showError("game_invalid");
    if (photos.length < MIN_PHOTOS || photos.length > MAX_PHOTOS) return showError("photo_count");

    const form = new FormData();
    form.set("game_id", game.id);
    const edition = document.getElementById("edition").value;
    if (edition.startsWith("new:")) form.set("new_edition", edition.slice(4));   // one of the game's IGDB editions
    else form.set("edition_id", edition);
    for (const name of ["condition", "price", "description"]) form.set(name, document.getElementById(name).value);
    photos.forEach(file => form.append("photos", file));

    const button = document.getElementById("publish");
    button.disabled = true;
    button.textContent = t("sell_publishing");
    const response = await fetch("/api/listings", { method: "POST", body: form, headers: { "X-Requested-With": "fetch" } });
    const data = await response.json().catch(() => ({}));
    button.disabled = false;
    button.textContent = t("sell_publish");
    if (response.ok) return location.assign(`/listing/${data.id}`);
    showError(response.status === 413 ? "photo_too_big" : data.error || "unknown");
};

// --- start -------------------------------------------------------------------------------
async function start() {
    applyI18n();
    renderPreviews();
    await renderAccountArea();
    if (!currentUser) return location.replace(`/account?next=${encodeURIComponent(location.pathname + location.search)}`);
    document.getElementById("condition").innerHTML =
        CONDITIONS.map(c => `<option value="${c}" ${c === "good" ? "selected" : ""}>${esc(conditionLabel(c))}</option>`).join("");
    const params = new URLSearchParams(location.search);
    const gameId = Number(params.get("game_id"));
    if (gameId) chooseGame(gameId, Number(params.get("edition_id")) || null);
}
start();
