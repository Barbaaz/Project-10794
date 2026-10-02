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

// "★ 4,5 (12)" next to a seller's name; nothing until they have a rating
function ratingBadge(rating, count) {
    if (!count) return "";
    return `<span class="text-warning-emphasis" title="${esc(t("rating_title", { rating: fmtNumber(rating), count }))}">★ ${fmtNumber(rating)} (${count})</span>`;
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
                <img src="${esc(photo?.thumb_url || "")}" alt="" loading="lazy" class="card-img-top">
                <div class="card-body p-2 d-flex flex-column">
                    <div class="fw-semibold listing-title" title="${esc(name)}">${esc(name)}</div>
                    <div class="small text-body-secondary mb-1">${esc(listing.platform_name)}</div>
                    <div class="d-flex justify-content-between align-items-center gap-1 mt-auto">
                        <strong class="fs-5">${eur.format(listing.price)}</strong>${statusBadge(listing.status)}
                    </div>
                    <div class="small">${esc(conditionLabel(listing.condition))}</div>
                    ${showSeller ? `<div class="small text-body-secondary text-truncate">${esc(sellerName(listing))}
                        ${ratingBadge(listing.seller_rating, listing.seller_rating_count)}</div>` : ""}
                </div>
            </a>
        </div>`;
}
