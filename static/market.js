/*
 * The pre-owned marketplace's shared pieces (game page, listing page, sell page, account page):
 * condition names, status badges, and the small listing card. Needs common.js and i18n.js.
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
    return listing.seller_name && listing.seller_name !== listing.seller_username
        ? `${listing.seller_name} (@${listing.seller_username})` : `@${listing.seller_username}`;
}

// A card linking to the listing: first photo, price, condition, seller (or the game, for "my listings")
function listingCard(listing, { showGame = false } = {}) {
    const photo = listing.photos[0];
    const subtitle = showGame
        ? `${esc(listing.title)}${listing.edition && listing.edition !== "Standard" ? ` — ${esc(listing.edition)}` : ""} · ${esc(listing.platform_name)}`
        : esc(sellerName(listing));
    return `
        <div class="col">
            <a href="/listing/${listing.id}" class="card h-100 shadow-sm text-decoration-none listing-card">
                <img src="${esc(photo?.thumb_url || "")}" alt="" loading="lazy" class="card-img-top">
                <div class="card-body p-2">
                    <div class="d-flex justify-content-between align-items-center gap-1">
                        <strong class="fs-5">${eur.format(listing.price)}</strong>${statusBadge(listing.status)}
                    </div>
                    <div class="small">${esc(conditionLabel(listing.condition))}</div>
                    <div class="small text-body-secondary text-truncate">${subtitle}</div>
                </div>
            </a>
        </div>`;
}
