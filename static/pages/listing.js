// The listing page (templates/listing.html). A file, not inline: the site's CSP only runs scripts from files.
const LISTING_ID = Number(document.body.dataset.listingId);
let listing;

async function load() {
    await renderAccountArea();
    const response = await fetch(`/api/listings/${LISTING_ID}`);
    document.getElementById("loading").classList.add("d-none");
    if (!response.ok) {
        document.getElementById("error").textContent = t("listing_not_found");
        document.getElementById("error").classList.remove("d-none");
        return;
    }
    listing = await response.json();
    render();
    compareWithStores();
}

function render() {
    document.title = `${listing.title} · ${eur.format(listing.price)} · Game Price Tracker`;
    const edition = listing.edition && listing.edition !== "Standard" ? ` — ${listing.edition}` : "";
    document.getElementById("title").textContent = listing.title + edition;
    document.getElementById("subtitle").textContent = listing.platform_name;
    document.getElementById("price").textContent = eur.format(listing.price);
    document.getElementById("status").innerHTML = statusBadge(listing.status);
    document.getElementById("condition").textContent = conditionLabel(listing.condition);
    // the seller links to their profile (ratings, other listings)
    document.getElementById("seller").innerHTML =
        `${listing.seller_username ? `<a href="/user/${encodeURIComponent(listing.seller_username)}">${esc(sellerName(listing))}</a>` : esc(sellerName(listing))}
         ${ratingBadge(listing.seller_rating, listing.seller_rating_count)}
         <div class="text-body-secondary">${esc(t("member_since").toLowerCase())} ${new Date(listing.seller_since).toLocaleDateString(LOCALE)}</div>`;
    document.getElementById("published").textContent = new Date(listing.created_at).toLocaleDateString(LOCALE);
    document.getElementById("description").textContent = listing.description || "";

    const gameLink = document.getElementById("game-link");
    gameLink.href = `/game/${listing.game_id}`;
    gameLink.textContent = t("listing_store_prices");
    gameLink.classList.remove("d-none");

    renderGallery(0);
    if (currentUser && currentUser.id === listing.user_id) {
        if (listing.removed_by_moderator) document.getElementById("removed-notice").classList.remove("d-none");
        else renderOwner();
    } else if (listing.seller_username) {       // a deleted seller's: nothing to ask or report any more
        renderBuyerActions();
        document.getElementById("report").innerHTML = reportButton("listing", listing.id);
    }
    document.getElementById("listing").classList.remove("d-none");
}

function renderGallery(selected) {
    const photo = listing.photos[selected];
    document.getElementById("main-photo").src = photo?.url || "";
    document.getElementById("main-photo").classList.toggle("d-none", !photo);    // a deleted seller's: none left
    document.getElementById("main-photo").alt = t("photo_n", { n: selected + 1 });
    const thumbs = document.getElementById("thumbs");
    thumbs.innerHTML = listing.photos.map((p, i) => `
        <button type="button" data-i="${i}" aria-current="${i === selected}" aria-label="${esc(t("photo_n", { n: i + 1 }))}">
            <img src="${esc(p.thumb_url)}" alt=""></button>`).join("");
    thumbs.querySelectorAll("[data-i]").forEach(b => b.onclick = () => renderGallery(Number(b.dataset.i)));
}

// "New at the stores: €X (Press Start)": the cheapest new copy in stock of the same edition
async function compareWithStores() {
    const game = await fetch(`/api/games/${listing.game_id}`).then(r => r.ok ? r.json() : null).catch(() => null);
    const edition = game?.editions.find(e => e.id === listing.edition_id) || game?.editions[0];
    const best = edition?.offers.find(o => o.in_stock && o.condition === "new");
    if (!best) return;
    document.getElementById("compare").innerHTML =
        `${esc(t("listing_new_in_stores"))} <strong>${eur.format(best.price)}</strong> · ${esc(best.store_name)}`;
}

// --- buyers: Message / Buy -------------------------------------------------------------------
// Both open the conversation with the seller (Buy also asks to buy); logged out: log in first
function renderBuyerActions() {
    document.getElementById("buyer-actions").classList.remove("d-none");
    const buy = document.getElementById("buy-btn");
    buy.disabled = listing.status !== "active";
    if (buy.disabled) buy.title = t("listing_unavailable_hint");
    buy.onclick = () => contactSeller(true);
    document.getElementById("message-btn").onclick = () => contactSeller(false);
}

async function contactSeller(buy) {
    if (!currentUser) return location.assign(`/account?next=${encodeURIComponent(location.pathname)}`);
    const { ok, data } = await api(`/api/listings/${LISTING_ID}/conversation`, { body: { buy } });
    if (ok) return location.assign(`/messages?c=${data.id}`);
    const box = document.getElementById("buyer-error");
    box.textContent = t(`error_${data?.error || "unknown"}`);
    box.classList.remove("d-none");
}

// --- the seller's controls ----------------------------------------------------------------
function ownerError(code) {
    const box = document.getElementById("owner-error");
    box.textContent = t(`error_${code || "unknown"}`);
    box.classList.toggle("d-none", !code);
}

async function change(request) {
    ownerError(null);
    const response = await request;
    const data = await (response.json ? response.json() : response.data);
    if (!(response.ok)) return ownerError(data?.error);
    listing = data;
    render();
}

function renderOwner() {
    document.getElementById("owner").classList.remove("d-none");
    document.getElementById("new-price").value = listing.price;
    document.getElementById("price-form").onsubmit = e => {
        e.preventDefault();
        change(api(`/api/listings/${LISTING_ID}`, { method: "PATCH", body: { price: document.getElementById("new-price").value } }));
    };

    // the statuses it can move to from here
    const next = { active: ["reserved", "sold", "removed"], reserved: ["active", "sold", "removed"], sold: ["active"], removed: ["active"] };
    const buttons = document.getElementById("status-buttons");
    buttons.innerHTML = next[listing.status].map(s => `
        <button type="button" class="btn btn-sm ${s === "removed" ? "btn-danger" : "btn-secondary"}" data-status="${s}">
            ${t(`listing_mark_${s}`)}</button>`).join("");
    buttons.querySelectorAll("[data-status]").forEach(b => b.onclick = () => {
        if (b.dataset.status === "removed" && !confirm(t("listing_remove_confirm"))) return;
        change(api(`/api/listings/${LISTING_ID}`, { method: "PATCH", body: { status: b.dataset.status } }));
    });

    const photos = document.getElementById("owner-photos");
    photos.innerHTML = listing.photos.map(p => `
        <figure><img src="${esc(p.thumb_url)}" alt="">
            <button type="button" class="btn btn-sm btn-danger" data-photo="${p.id}" aria-label="${esc(t("remove_photo"))}">✕</button>
        </figure>`).join("");
    photos.querySelectorAll("[data-photo]").forEach(b => b.onclick = () =>
        change(api(`/api/listings/${LISTING_ID}/photos/${b.dataset.photo}`, { method: "DELETE" })));

    document.getElementById("add-photos").onchange = e => {
        const form = new FormData();
        [...e.target.files].forEach(f => form.append("photos", f));
        e.target.value = "";
        change(fetch(`/api/listings/${LISTING_ID}/photos`, { method: "POST", body: form, headers: { "X-Requested-With": "fetch" } }));
    };
}

applyI18n();
load();
