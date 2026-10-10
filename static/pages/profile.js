// The profile page (templates/profile.html). A file, not inline: the site's CSP only runs scripts from files.
const USERNAME = document.body.dataset.username;
let USER_ID = null;

function stars(n) {
    return `<span class="text-warning" aria-label="${esc(t("stars_n", { n }))}">${"★".repeat(n)}${"☆".repeat(5 - n)}</span>`;
}

async function load() {
    await renderAccountArea();
    const response = await fetch(`/api/users/${encodeURIComponent(USERNAME)}`);
    document.getElementById("loading").classList.add("d-none");
    if (!response.ok) return document.getElementById("error").classList.remove("d-none");
    const user = await response.json();
    USER_ID = user.id;
    document.title = `@${user.username} · Game Price Tracker`;
    document.getElementById("name").textContent =
        user.display_name !== user.username ? `${user.display_name} (@${user.username})` : `@${user.username}`;
    document.getElementById("since").textContent =
        `${t("member_since")} ${new Date(user.created_at).toLocaleDateString(LOCALE)}`;
    document.getElementById("average").innerHTML = user.rating_count ? `★ ${fmtNumber(user.rating)}` : "—";
    document.getElementById("count").textContent = t("profile_rating_count", { count: user.rating_count });

    const mine = currentUser && currentUser.id === user.id;     // the person can answer their ratings
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
    if (!response.ok) return;
    const { items, stats } = await response.json();
    document.getElementById("collection-summary").textContent =
        t("profile_collection_summary", { owned: stats.owned, completed: stats.completed, wishlist: stats.wishlist });
    const owned = items.filter(i => i.kind === "owned").sort((a, b) => (a.name || "").localeCompare(b.name || "", LOCALE));
    document.getElementById("collection-items").innerHTML = owned.map(i => `
        <li class="list-group-item px-0 d-flex justify-content-between gap-2">
            <a href="/game/${i.game_id}">${esc(localName(i) || "")}</a>
            <span class="text-body-secondary text-nowrap">${esc(i.platform_name || "")}${i.status ? ` · ${esc(t(`status_play_${i.status}`))}` : ""}</span>
        </li>`).join("");
    document.getElementById("collection").classList.remove("d-none");
}

applyI18n();
load();
