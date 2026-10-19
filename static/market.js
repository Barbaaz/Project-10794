/*
 * The pre-owned marketplace's shared pieces (game page, listing page, sell page, account page):
 * condition names, status badges, the small listing card, the report dialog and a wish's target price. Needs common.js
 * and i18n.js.
 */

const CONDITIONS = ["new", "like_new", "good", "fair", "poor"];

function conditionLabel(condition) {
    return t(`condition_${condition}`);
}

// Reserved / sold / removed get a badge; an active listing doesn't need one
function statusBadge(status) {
    const styles = { reserved: "text-bg-warning", sold: "text-bg-secondary", removed: "text-bg-dark" };
    return styles[status] ? `<span class="badge ${styles[status]}">${t(`status_${status}`)}</span>` : "";
}

function sellerName(listing) {
    if (!listing.seller_username) return t("deleted_user");     // the seller deleted their account since
    return listing.seller_name && listing.seller_name !== listing.seller_username
        ? `${listing.seller_name} (@${listing.seller_username})` : `@${listing.seller_username}`;
}

// "★ 4,5 (12)" next to a seller's name; nothing until they have a rating
function ratingBadge(rating, count) {
    if (!count) return "";
    return `<span class="text-warning-emphasis" title="${esc(t("rating_title", { rating: fmtNumber(rating), count }))}">★ ${fmtNumber(rating)} (${count})</span>`;
}

// --- reporting a listing, a user or a rating to the moderators (app/services/moderation_service.py) ---
const REPORT_REASONS = ["fake", "scam", "offensive", "wrong_game", "prohibited", "other"];

// A small "Report" link; clicking it opens the report dialog (logged out: log in first)
function reportButton(kind, id) {
    return `<button type="button" class="btn btn-link btn-sm p-0 text-body-secondary small" data-report-kind="${kind}"
                data-report-id="${id}">${icon("flag", 14)} ${esc(t("report"))}</button>`;
}

document.addEventListener("click", e => {
    const button = e.target.closest("[data-report-kind]");
    if (button) openReport(button.dataset.reportKind, Number(button.dataset.reportId));
});

function openReport(kind, id) {
    if (!currentUser) return location.assign(`/account?next=${encodeURIComponent(location.pathname)}`);
    document.getElementById("report-dialog")?.remove();
    const dialog = document.createElement("dialog");
    dialog.id = "report-dialog";
    dialog.className = "border rounded shadow p-0 bg-body text-body";
    dialog.style.maxWidth = "28rem";
    dialog.innerHTML = `
        <form method="dialog" class="p-3">
            <h2 class="h5">${esc(t(`report_title_${kind}`))}</h2>
            <fieldset class="mb-2">
                <legend class="form-label small">${esc(t("report_reason"))}</legend>
                ${REPORT_REASONS.map((r, i) => `<div class="form-check">
                    <input class="form-check-input" type="radio" name="reason" id="reason-${r}" value="${r}" ${i ? "" : "required"}>
                    <label class="form-check-label" for="reason-${r}">${esc(t(`reason_${r}`))}</label></div>`).join("")}
            </fieldset>
            <label for="report-details" class="form-label small">${esc(t("report_details"))}</label>
            <textarea id="report-details" name="details" maxlength="1000" rows="3" class="form-control form-control-sm mb-2"></textarea>
            <div class="alert d-none py-1 px-2 small" role="alert"></div>
            <div class="d-flex justify-content-end gap-2">
                <button type="button" value="cancel" class="btn btn-sm btn-secondary">${esc(t("cancel"))}</button>
                <button type="submit" class="btn btn-sm btn-danger">${esc(t("report_send"))}</button>
            </div>
        </form>`;
    document.body.append(dialog);
    const form = dialog.querySelector("form");
    const message = dialog.querySelector(".alert");
    dialog.querySelector("[value=cancel]").onclick = () => dialog.close();
    form.onsubmit = async e => {
        e.preventDefault();
        const { ok, data } = await api("/api/reports", {
            body: { kind, target_id: id, reason: form.reason.value, details: form.details.value } });
        message.className = `alert ${ok ? "alert-success" : "alert-warning"} py-1 px-2 small`;
        message.textContent = ok ? t("report_sent") : t(`error_${data?.error || "unknown"}`);
        if (ok) {
            form.querySelector("[type=submit]").remove();
            setTimeout(() => dialog.close(), 1500);
        }
    };
    dialog.showModal();
}

// A card linking to the listing. Like the catalogue cards: the game's name first under the photo,
// then platform, price (and status), condition, and the seller with their rating
// (showSeller: false on the seller's own "my listings")
function listingCard(listing, { showSeller = true } = {}) {
    const photo = listing.photos[0];
    const edition = listing.edition && listing.edition !== "Standard" ? ` — ${listing.edition}` : "";
    const name = listing.title + edition;
    return `
        <div class="col">
            <a href="/listing/${listing.id}" class="card h-100 shadow-sm text-decoration-none listing-card">
                <img src="${esc(photo?.thumb_url || "")}" alt="" loading="lazy" class="card-img-top ${photo ? "" : "invisible"}">
                <div class="card-body p-2 d-flex flex-column">
                    <div class="fw-semibold listing-title" title="${esc(name)}">${esc(name)}</div>
                    <div class="small text-body-secondary mb-1">${esc(listing.platform_name)}</div>
                    <div class="d-flex justify-content-between align-items-center gap-1 mt-auto">
                        <strong class="fs-5">${eur.format(listing.price)}</strong>${statusBadge(listing.status)}
                    </div>
                    <div class="small">${esc(conditionLabel(listing.condition))}</div>
                    ${showSeller ? `<div class="small text-body-secondary text-truncate">${avatarImage(listing.seller_avatar, 18)} ${esc(sellerName(listing))}
                        ${ratingBadge(listing.seller_rating, listing.seller_rating_count)}</div>` : ""}
                </div>
            </a>
        </div>`;
}

// Finding a game for the sell form and the collection: the catalogue's games as you type, and for a
// game we don't have (older platforms, games no store sells) IGDB's, with a button per platform;
// picking one creates the game there (app/services/igdb_game_service.py). Never a typed name.
// els: {search, results, igdbButton, igdbResults}; onPick(gameId, editionId or null); onError(code)
function gamePicker(els, onPick, onError) {
    let timer;
    els.search.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(() => searchCatalogue(els.search.value.trim()), 250);
    });

    async function searchCatalogue(q) {
        els.igdbResults.innerHTML = "";
        els.igdbButton.classList.toggle("d-none", q.length < 2);
        if (q.length < 2) { els.results.innerHTML = ""; return; }
        const { games } = await fetch(`/api/games?q=${encodeURIComponent(q)}&per_page=8`).then(r => r.json());
        if (els.search.value.trim() !== q) return;        // typed on meanwhile
        els.results.innerHTML = games.map(g => `
            <button type="button" class="list-group-item list-group-item-action d-flex align-items-center gap-2 game-option" data-id="${g.id}">
                <img src="${esc(g.image || "")}" alt="">
                <span>${esc(g.title)} <span class="text-body-secondary small">· ${esc(g.platform)}</span></span>
            </button>`).join("") || `<div class="list-group-item small text-body-secondary">${t("no_results")}</div>`;
        els.results.querySelectorAll("[data-id]").forEach(b => b.onclick = () => onPick(Number(b.dataset.id), null));
    }

    els.igdbButton.onclick = async () => {
        const list = els.igdbResults;
        list.innerHTML = `<div class="list-group-item small text-body-secondary">${t("sell_igdb_searching")}</div>`;
        const response = await fetch(`/api/igdb/games?q=${encodeURIComponent(els.search.value.trim())}`);
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
            if (!ok) return onError(data?.error || "unknown");
            list.innerHTML = "";
            onPick(data.game_id, data.edition_id);
        });
    };

    // back to an empty search (after a pick)
    return () => {
        els.search.value = "";
        els.results.innerHTML = els.igdbResults.innerHTML = "";
        els.igdbButton.classList.add("d-none");
    };
}

// --- a wish's target price (user, 2026-10-16): the wishlist page and the game page's "Quero" ---
// The window's content: the game, what it costs now (the cheapest, new or used: what the target is compared
// with, collection_service.target_hit) and the price; bindTargetForm saves it
function targetForm({ image, name, platform, now, target }) {
    return `
        <div class="d-flex gap-3 align-items-start">
            ${image ? `<img class="dialog-cover ${coverClass(image)}" src="${esc(image)}" alt="">` : ""}
            <div class="flex-grow-1 min-w-0">
                <h2 id="item-dialog-title" class="h5 mb-0">${esc(t("target_title"))}</h2>
                <div class="small">${esc(name || "")}</div>
                <div class="small text-body-secondary">${esc(platform || "")}${now != null
                    ? ` · ${esc(t("target_now", { price: eur.format(now) }))}` : ""}</div>
            </div>
            <button type="button" class="btn-close" data-close aria-label="${esc(t("collection_edit_done"))}"></button>
        </div>
        <form class="mt-3" novalidate>
            <label class="form-label small mb-1" for="target-price">${esc(t("target_label"))}</label>
            <div class="input-group input-group-sm" style="max-width: 14rem;">
                <input id="target-price" name="target" type="text" inputmode="decimal" class="form-control"
                       value="${esc(target ? fmtNumber(target) : "")}"
                       placeholder="${esc(fmtNumber(20))}" aria-describedby="target-help"><span class="input-group-text">€</span></div>
            <div id="target-help" class="small text-body-secondary mt-1">${esc(t("target_help"))}</div>
            <div class="d-flex align-items-center gap-2 border-top pt-2 mt-3">
                ${target ? `<button type="button" class="btn btn-link btn-sm text-danger px-0" data-clear>${esc(t("target_clear"))}</button>` : ""}
                <span class="small text-danger ms-auto" data-error role="status"></span>
                <button type="submit" class="btn btn-primary btn-sm">${esc(t("target_save"))}</button>
            </div>
        </form>`;
}

// Saves the target (or clears it) on the wish; done(target) after, the window then closes
function bindTargetForm(dialog, body, itemId, done) {
    const form = body.querySelector("form");
    const save = async target => {
        const { ok, data } = await api(`/api/collection/${itemId}`, { method: "PATCH", body: { target_price: target } });
        if (!ok) return body.querySelector("[data-error]").textContent = t(`error_${data?.error || "unknown"}`);
        done(target);
        dialog.close();
        showNotifications();           // the header's bell counts again
    };
    form.onsubmit = event => { event.preventDefault(); save(form.target.value.trim() || null); };
    body.querySelector("[data-clear]")?.addEventListener("click", () => save(null));
    body.querySelectorAll("[data-close]").forEach(b => b.onclick = () => dialog.close());
    dialog.showModal();
    form.target.focus();
}
