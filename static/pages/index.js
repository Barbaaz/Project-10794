// The index page (templates/index.html). A file, not inline: the site's CSP only runs scripts from files.
// t(), eur, LOCALE, fmtNumber: static/i18n.js

let currentData = null;     // the search results on screen (a catalogue page)
let hasSearched = false;
let stores = {};
let genres = [];     // categories with games in stock (/api/genres), for the category filter
let tags = [];       // tags for the tag filter (/api/tags): game modes, themes, prices
let collectionIds = {};     // the user's collection: {edition_id: {owned?: item id, wishlist?: item id}} (loadCollectionIds)
// esc(), storeName(), saved() / save(), toggleDark(): static/common.js

function handleSearch(event) {
    event.preventDefault();
    search();
}

// A card: cover, platform, title and edition, the best store price (the game page has them all).
// group = {name, console, platform_name, game_id, edition_id, offers: [...]}
// extraLine: null = no extra line; "" = keep the space, so cards in the same grid line up

// A game on several platforms is one card (the catalogue's `alternatives`): its platforms as chips,
// pressing one shows that platform's offers, cover and ☆ menu. again(group): the card for another
// platform, made the way the caller made this one (its badges)
function makeCard(group, { coverBadge = "", extraLine = null, again = null } = {}) {
    // in stock first, then cheapest
    const offers = [...group.offers].sort((a, b) => (b.in_stock - a.in_stock) || (a.price - b.price));
    const best = offers[0];
    const gameUrl = `/game/${group.game_id}`;

    // The best store price, large, with its store and how many stores sell it (all of them on the game
    // page); the copies users sell on a line of their own (see usedLine)
    const used = group.used;
    const [title, edition] = splitEdition(localName(group));
    const stock = offers.filter(o => o.in_stock).length;
    const lead = best ? leadOffer(best, coverBadge, offers.length > 1 ? t("in_stores", { count: stock || offers.length }) : "") : "";
    const none = offers.length || used ? "" : `<div class="small text-body-secondary">${t("no_offers")}</div>`;

    const col = document.createElement("div");
    col.className = "col";
    col.innerHTML = `
        <div class="h-100 game-card d-flex flex-column${isStaff() && mergePick().edition_id === group.edition_id ? " merge-picked" : ""}"
             data-edition-id="${group.edition_id}">
            <div class="position-relative">
                <a href="${gameUrl}" class="cover-link" tabindex="-1" aria-hidden="true"><img src="${esc(group.cover || best?.image || group.image || "")}"
                    class="${coverClass(group.cover || best?.image || group.image)}" alt="" loading="lazy"></a>
                ${coverBadge}
                ${group.at_historical_low ? `<span class="badge low-price-badge"
                    title="${esc(t("low_badge_hint"))}">${t("low_badge")}</span>` : ""}
                <button type="button" class="btn btn-light fav-btn shadow-sm" data-edition="${group.edition_id}"
                    aria-label="${t("card_menu")}" aria-haspopup="menu" aria-expanded="false">${starButton(group)}</button>
            </div>
            <div class="card-text d-flex flex-column flex-grow-1">
                ${platformLine(group)}
                <a href="${gameUrl}" class="link-body-emphasis text-decoration-none game-title" title="${esc(localName(group))}">${esc(title)}</a>
                <div class="card-edition">${esc(edition) || "&nbsp;"}</div>
                ${extraLine === null ? "" : `<div class="small card-extra">${extraLine}</div>`}
                <div class="mt-auto pt-2">${lead}${used ? usedLine(group) : ""}${none}</div>
            </div>
            ${isStaff() ? `<button type="button" class="btn btn-sm admin-card-btn" aria-label="${esc(t("admin_card_menu"))}"
                                   title="${esc(t("admin_card_menu"))}" aria-haspopup="menu" aria-expanded="false">${icon("more")}</button>` : ""}
        </div>`;
    col.querySelector(".fav-btn").onclick = e => toggleCardMenu(e.currentTarget, group);
    const adminButton = col.querySelector(".admin-card-btn");
    if (adminButton) adminButton.onclick = e => toggleCardMenu(e.currentTarget, group, fillAdminMenu);
    col.querySelectorAll("[data-platform-index]").forEach(chip => chip.onclick = () => {
        const all = platformsOf(group);
        const i = Number(chip.dataset.platformIndex);
        const next = { ...all[i], alternatives: [], _all: all };
        const card = again ? again(next) : makeCard(next, { coverBadge, extraLine });
        col.replaceWith(card);
        card.querySelector(`[data-platform-index="${i}"]`)?.focus();
    });
    return col;
}

function platformLine(group) {
    const reviews = group.review_count
        ? `<span title="${esc(t("review_score_hint", { count: group.review_count }))}">${fmtNumber(group.review_score)}/10 (${group.review_count})</span>` : "";
    const all = platformsOf(group);
    if (!all) {
        return `<div class="card-platform">${esc(group.platform_name || group.console)}${reviews ? ` · ${reviews}` : ""}</div>`;
    }
    const chips = all.map((g, i) => {
        const on = g.edition_id === group.edition_id;
        return `<button type="button" class="btn btn-sm platform-chip ${on ? "btn-primary" : "btn-secondary"}" data-platform-index="${i}"
            aria-pressed="${on}" title="${esc(g.platform_name)}">${esc(PLATFORM_SHORT[g.console] || g.platform_name)}</button>`;
    }).join("");
    return `<div class="platform-chips d-flex flex-wrap gap-1" role="group" aria-label="${esc(t("platforms"))}">${chips}</div>
        ${reviews ? `<div class="text-body-secondary small">${reviews}</div>` : ""}`;
}

// A store's discount on the price itself, unless the cover already says it
const discountTag = (o, coverBadge) => o.discount_percent && !coverBadge
    ? `<span class="badge text-bg-danger me-1">-${o.discount_percent}%</span>` : "";

// "Metroid Ravenous — Special Edition" → ["Metroid Ravenous", "Special Edition"] (the API joins them so)
function splitEdition(name) {
    const at = (name || "").lastIndexOf(" — ");
    return at < 0 ? [name || "", ""] : [name.slice(0, at), name.slice(at + 3)];
}

// The best offer: its price large, the store (and "used" / "sold out", how many stores) under it
function leadOffer(o, coverBadge, stores = "") {
    return `
        <a href="${esc(o.url)}" target="_blank" rel="noopener" class="lead-offer ${o.in_stock ? "" : "out"}"
           title="${esc(t("view_at", { store: storeName(o.store) }))}">
            <span class="amount">${discountTag(o, coverBadge)}${eur.format(o.price)}${o.was_price ? ` <s class="was">${eur.format(o.was_price)}</s>` : ""}</span>
            <span class="where">${esc(storeName(o.store))}${o.condition === "used" ? ` · ${t("used")}` : ""}${o.in_stock ? "" : ` · ${t("sold_out")}`}${stores ? ` · ${esc(stores)}` : ""}</span>
        </a>`;
}

// "Usados desde 18,99 €": the copies users sell; one → that listing, several → the game page's list
function usedLine(group) {
    const { count, price, listing_id } = group.used;
    const href = count === 1 ? `/listing/${listing_id}` : `/game/${group.game_id}#market`;
    return `<a href="${href}" class="used-line" title="${esc(t("used_title", { count }))}">${esc(t("used_from_price", { price: eur.format(price) }))}</a>`;
}

// A game edition users sell, like the catalogue cards: cover, platform (chips when sold on several:
// /api/listings' `alternatives`), name, then the cheapest copy large (seller and rating, condition) and
// how many sellers
function marketCard(group) {
    const seller = l => `@${esc(l.seller_username)}${l.seller_rating_count ? ` ★${fmtNumber(l.seller_rating)}` : ""}`;
    const first = group.listings[0];
    const [title, edition] = splitEdition(localName(group));
    const lead = `
        <a href="/listing/${first.id}" class="lead-offer" title="${esc(`${sellerName(first)} · ${conditionLabel(first.condition)}`)}">
            <span class="amount">${eur.format(first.price)}</span>
            <span class="where">${seller(first)} · ${esc(conditionLabel(first.condition))}</span>
        </a>`;
    const more = group.listings.length > 1
        ? `<a href="/game/${group.game_id}#market" class="used-line">${t("sellers_count", { count: group.listings.length })}</a>` : "";
    const cover = group.image || first.photos[0]?.thumb_url || "";
    const col = document.createElement("div");
    col.className = "col";
    col.innerHTML = `
        <div class="h-100 game-card d-flex flex-column">
            <a href="/game/${group.game_id}#market" class="cover-link" tabindex="-1" aria-hidden="true"><img src="${esc(cover)}" alt="" loading="lazy"></a>
            <div class="card-text d-flex flex-column flex-grow-1">
                ${platformLine(group)}
                <a href="/game/${group.game_id}#market" class="link-body-emphasis text-decoration-none game-title"
                   title="${esc(localName(group))}">${esc(title)}</a>
                <div class="card-edition">${esc(edition) || "&nbsp;"}</div>
                <div class="mt-auto pt-2">${lead}${more}</div>
            </div>
        </div>`;
    col.querySelectorAll("[data-platform-index]").forEach(chip => chip.onclick = () => {
        const all = platformsOf(group);
        const i = Number(chip.dataset.platformIndex);
        const card = marketCard({ ...all[i], alternatives: [], _all: all });
        col.replaceWith(card);
        card.querySelector(`[data-platform-index="${i}"]`)?.focus();
    });
    return col;
}

// ---------------------------------------------------------------------------
// Front page tabs
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Catalogue tabs: every edition in stock (or only special editions), 48 at a time,
// filtered by the platform selector on the server, sortable
// ---------------------------------------------------------------------------

const CATALOG_PAGE = 48;
let catalogSort = saved("catalogSort", "name");
// Store filter for the catalogue tabs and the search (/?…&store=cstech); not remembered between visits
let catalogStore = new URLSearchParams(location.search).get("store") || "";
// Category, tag and PEGI filters (/?…&genre=rpg&tags=coop&pegi=12), the same way
let catalogGenre = new URLSearchParams(location.search).get("genre") || "";
let catalogTag = new URLSearchParams(location.search).get("tags") || "";
let catalogPegi = new URLSearchParams(location.search).get("pegi") || "";
const PEGI_AGES = [3, 7, 12, 16, 18];
const MAX_TAGS = 5;      // as many as /api/games/catalog takes

// The filters other than platform and sort: [address / API parameter, current value]
// The catalogue filters' panel on a phone: closed until "Filtros" is pressed (kept open while paging)
let filtersOpen = false;

function extraFilters() {
    // the platform too (user, 2026-10-13: a refresh, as after a merge, stays on it); the consoles tab has no
    // game filters (category, tags, PEGI)
    const platform = ["platform", document.getElementById("consoleFilter").value];
    if (onHardwareTab()) return [platform, ["store", catalogStore]];
    return [platform, ["store", catalogStore], ["genre", catalogGenre], ["tags", catalogTag], ["pegi", catalogPegi]];
}

// Consoles (user, 2026-10-07): their own tab
function onHardwareTab() {
    return frontTab === "hardware" && !document.getElementById("q").value.trim();     // a search lists games
}

// /?tab=catalog&page=3 opens on that page (bookmarks, the game page's back button)
// (a page in a search address, /?q=zelda&page=2, belongs to the search, not to the tab)
const startParams = new URLSearchParams(location.search);
let pageFromUrl = startParams.get("q") ? 1 : Number(startParams.get("page")) || 1;

function catalogTab(special, empty, hardware = false) {
    return {
        platformAware: true,
        paged: true,
        load: platform => {
            const page = pageFromUrl;
            pageFromUrl = 1;    // only for the first load
            return loadCatalogPage(special, platform, page, hardware);
        },
        render: renderCatalog,
        empty,
    };
}

async function showCatalogPage(page) {
    const data = frontData[frontTab];
    frontData[frontTab] = await loadCatalogPage(data.special, data.platform, page, data.hardware);
    setPageUrl(listUrl({ tab: frontTab }, page));
    renderFront();
    document.getElementById("front").scrollIntoView({ block: "start" });
}

// /browse?tab=catalog&page=3&platform=PS5&store=cstech&genre=rpg or /browse?q=zelda&page=2: each only when not the default
function listUrl(params, page = 1) {
    const query = new URLSearchParams(params);
    if (page > 1) query.set("page", page);
    for (const [name, value] of extraFilters()) if (value) query.set(name, value);
    return `/browse?${query}`;
}

// « Anterior  1 … 4 5 [6] 7 8 … 75  Seguinte »  (solid buttons, current page in blue). Each "…" is a button
// too: pressed, it turns into a box the size of a page button to type any page in (user, 2026-10-13)
function pagination(page, pages, showPage) {
    const nav = document.createElement("nav");
    nav.className = "d-flex flex-wrap justify-content-center gap-1 mt-4";
    nav.setAttribute("aria-label", t("pages"));
    if (!Number.isInteger(pages) || pages <= 1) return nav;

    const shown = new Set([1, pages]);
    for (let p = page - 2; p <= page + 2; p++) if (p >= 1 && p <= pages) shown.add(p);
    const numbers = [...shown].sort((a, b) => a - b);

    const button = (label, target, { current = false, disabled = false } = {}) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = `btn btn-sm ${current ? "btn-primary" : "btn-secondary"}`;
        b.textContent = label;
        b.disabled = disabled;
        if (current) b.setAttribute("aria-current", "page");
        if (!disabled && !current) b.onclick = () => showPage(target);
        return b;
    };
    const gap = () => {
        const b = button("…");
        const label = t("go_to_page", { pages });
        b.title = label;
        b.setAttribute("aria-label", label);
        b.onclick = () => {
            const box = document.createElement("input");
            box.type = "text";
            box.inputMode = "numeric";
            box.className = "form-control form-control-sm page-jump";
            box.setAttribute("aria-label", label);
            box.placeholder = "#";
            const back = () => box.isConnected && box.replaceWith(b);
            box.onkeydown = event => {
                if (event.key === "Escape") { back(); b.focus(); }
                if (event.key !== "Enter") return;
                const wanted = Math.round(Number(box.value));
                if (wanted >= 1) {
                    const target = Math.min(wanted, pages);
                    if (target !== page) showPage(target);
                    else back();
                }
            };
            box.onblur = () => { if (!box.value.trim()) back(); };
            b.replaceWith(box);
            box.focus();
        };
        return b;
    };

    nav.appendChild(button(t("previous"), page - 1, { disabled: page === 1 }));
    numbers.forEach((p, i) => {
        if (i > 0 && p - numbers[i - 1] > 1) nav.appendChild(gap());
        nav.appendChild(button(String(p), p, { current: p === page }));
    });
    nav.appendChild(button(t("next"), page + 1, { disabled: page === pages }));
    return nav;
}

// /api/games/catalog parameters: the chosen sort, page, platform and the other filters, plus `extra`
function catalogParams(page, platform, extra = {}) {
    const params = new URLSearchParams({ ...extra, sort: catalogSort, page, per_page: CATALOG_PAGE });
    if (platform) params.set("platform", platform);
    for (const [name, value] of extraFilters()) if (value) params.set(name, value);
    return params;
}

async function loadCatalogPage(special, platform, page, hardware = false) {
    const params = catalogParams(page, platform, special ? { editions: "special" } : {});
    if (hardware) params.set("kind", "hardware");
    const data = await fetch(`/api/games/catalog?${params}`).then(r => r.json());
    // pages is computed here too, in case the server is older than this page
    const pages = data.pages || Math.max(1, Math.ceil(data.total / (data.per_page || CATALOG_PAGE)));
    return { ...data, pages, special, platform, hardware };
}

// The catalogue tabs and the search results: count, store filter, sort, cards, page buttons.
// showPage(n) loads page n again with the current filters (the tab's or the search's)
// ---------------------------------------------------------------------------
// Market tab: every game users sell (active listings), 48 at a time, newest first or by price
// ---------------------------------------------------------------------------
let marketSort = saved("marketSort", "newest");
// games, consoles, or both ("")
let marketKind = saved("marketKind", "");

async function loadMarketPage(platform, page) {
    const params = new URLSearchParams({ sort: marketSort, page, per_page: CATALOG_PAGE });
    if (platform) params.set("platform", platform);
    if (marketKind) params.set("kind", marketKind);
    const data = await fetch(`/api/listings?${params}`).then(r => r.json());
    return { ...data, platform };
}

async function showMarketPage(page) {
    frontData.market = await loadMarketPage(frontData.market.platform, page);
    setPageUrl(listUrl({ tab: "market" }, page));
    renderFront();
    document.getElementById("front").scrollIntoView({ block: "start" });
}

function renderMarket(data) {
    const wrap = document.createElement("div");
    wrap.innerHTML = `
        <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
            <span class="small text-body-secondary me-auto">${esc(t("market_count",
                { count: fmtNumber(data.total), page: data.page, pages: data.pages }))}</span>
            <a href="/sell" class="btn btn-sm btn-success">${t("market_sell")}</a>
            <select id="market-kind" class="form-select form-select-sm w-auto" aria-label="${esc(t("type_filter"))}">
                <option value="">${t("market_kind_all")}</option>
                <option value="game">${t("market_kind_games")}</option>
                <option value="hardware">${t("market_kind_hardware")}</option>
            </select>
            <label class="small text-body-secondary" for="market-sort">${t("sort")}</label>
            <select id="market-sort" class="form-select form-select-sm w-auto">
                <option value="newest">${t("sort_newest")}</option>
                <option value="price_asc">${t("sort_price_asc")}</option>
                <option value="price_desc">${t("sort_price_desc")}</option>
            </select>
        </div>
        `;
    const grid = cardGrid();
    data.groups.forEach(group => grid.appendChild(marketCard(group)));
    wrap.appendChild(grid);
    const select = wrap.querySelector("#market-sort");
    select.value = marketSort;
    select.onchange = () => {
        marketSort = select.value;
        save("marketSort", marketSort);
        showMarketPage(1);
    };
    const kindSelect = wrap.querySelector("#market-kind");
    kindSelect.value = marketKind;
    kindSelect.onchange = () => {
        marketKind = kindSelect.value;
        save("marketKind", marketKind);
        showMarketPage(1);
    };
    wrap.appendChild(pagination(data.page, data.pages, showMarketPage));
    return wrap;
}

function renderCatalog(data, showPage = showCatalogPage) {
    const count = { count: fmtNumber(data.total), page: data.page, pages: data.pages, query: data.query };
    const storeOptions = Object.values(stores)      // active stores (/api/stores)
        .map(s => `<option value="${esc(s.slug)}">${esc(s.name)}</option>`).join("");
    const genreOptions = [...genres]
        .sort((a, b) => t(`genre_${a.genre}`).localeCompare(t(`genre_${b.genre}`), LOCALE))
        .map(g => `<option value="${esc(g.genre)}">${esc(t(`genre_${g.genre}`))}</option>`).join("");
    // Several tags at once (all must match): the dropdown adds one, its chip's × removes it
    const chosenTags = catalogTag.split(",").filter(Boolean);
    const tagOptions = ["mode", "theme", "price"].map(group => `<optgroup label="${esc(t(`tag_group_${group}`))}">
        ${tags.filter(x => x.group === group && !chosenTags.includes(x.tag))
            .map(x => `<option value="${esc(x.tag)}">${esc(t(`tag_${x.tag}`))}</option>`).join("")}</optgroup>`).join("");
    const tagChips = chosenTags.map(tag => `
        <span class="badge rounded-pill text-bg-primary d-inline-flex align-items-center gap-1">${esc(t(`tag_${tag}`))}
            <button type="button" class="btn-close btn-close-white" style="font-size: .55rem;" data-remove-tag="${esc(tag)}"
                    aria-label="${esc(t("remove_tag", { tag: t(`tag_${tag}`) }))}"></button></span>`).join("");
    const pegiOptions = PEGI_AGES.map(age => `<option value="${age}">${esc(t("pegi_up_to", { age }))}</option>`).join("");
    const hardware = data.hardware && !data.query;
    const wrap = document.createElement("div");
    const activeFilters = hardware ? [catalogStore].filter(Boolean).length
        : [catalogGenre, catalogPegi, catalogStore].filter(Boolean).length + chosenTags.length;
    // the game filters (category, tags, PEGI); the consoles tab only has the store's
    const kindFilters = hardware ? "" : `
            <div><label class="form-label small text-body-secondary mb-1" for="catalog-genre">${t("genre_filter")}</label>
                <select id="catalog-genre" class="form-select form-select-sm">
                    <option value="">${t("all_genres")}</option>${genreOptions}
                </select></div>
            <div><label class="form-label small text-body-secondary mb-1" for="catalog-tag">${t("tag_filter")}</label>
                <select id="catalog-tag" class="form-select form-select-sm" ${chosenTags.length >= MAX_TAGS ? "disabled" : ""}>
                    <option value="">${t(chosenTags.length ? "add_tag" : "all_tags")}</option>${tagOptions}
                </select></div>
            <div><label class="form-label small text-body-secondary mb-1" for="catalog-pegi">${t("pegi_filter")}</label>
                <select id="catalog-pegi" class="form-select form-select-sm">
                    <option value="">${t("all_ages")}</option>${pegiOptions}
                </select></div>`;
    wrap.innerHTML = `
        <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
            <span class="small text-body-secondary me-auto">${esc(t(data.query ? "search_count"
                : data.special ? "special_count" : hardware ? "hardware_count" : "catalog_count", count))}</span>
            <button type="button" class="btn btn-sm ${activeFilters ? "btn-primary" : "btn-secondary"} d-md-none" id="filters-toggle"
                    aria-expanded="${filtersOpen}" aria-controls="catalog-filters">${t("filters_button")}${activeFilters ? ` (${activeFilters})` : ""}</button>
            <label class="small text-body-secondary d-none d-sm-inline" for="catalog-sort">${t("sort")}</label>
            <select id="catalog-sort" class="form-select form-select-sm w-auto" aria-label="${esc(t("sort"))}">
                <option value="name">${t("sort_name")}</option>
                <option value="price_asc">${t("sort_price_asc")}</option>
                <option value="price_desc">${t("sort_price_desc")}</option>
            </select>
        </div>
        <div id="catalog-filters" class="catalog-filters mb-3 ${filtersOpen ? "open" : ""}">${kindFilters}
            <div><label class="form-label small text-body-secondary mb-1" for="catalog-store">${t("store_filter")}</label>
                <select id="catalog-store" class="form-select form-select-sm">
                    <option value="">${t("all_stores")}</option>${storeOptions}
                </select></div>
        </div>
        ${chosenTags.length && !hardware ? `<div class="d-flex flex-wrap gap-1 mb-3" aria-label="${esc(t("chosen_tags"))}">${tagChips}</div>` : ""}`;

    const toggle = wrap.querySelector("#filters-toggle");
    toggle.onclick = () => {
        filtersOpen = !filtersOpen;
        toggle.setAttribute("aria-expanded", filtersOpen);
        wrap.querySelector("#catalog-filters").classList.toggle("open", filtersOpen);
    };
    const select = wrap.querySelector("#catalog-sort");
    select.value = catalogSort;
    select.onchange = async () => {
        catalogSort = select.value;
        save("catalogSort", catalogSort);
        await showPage(1);
    };
    // Store, category, tag, PEGI: a change loads page 1 with the new choice
    const filterSelect = (id, value, set) => {
        const box = wrap.querySelector(id);
        box.value = value;
        box.onchange = async () => {
            set(box.value);
            await showPage(1);
        };
    };
    filterSelect("#catalog-store", catalogStore, v => catalogStore = v);
    if (!hardware) {
        filterSelect("#catalog-genre", catalogGenre, v => catalogGenre = v);
        filterSelect("#catalog-tag", "", v => catalogTag = [...chosenTags, v].filter(Boolean).join(","));
        wrap.querySelectorAll("[data-remove-tag]").forEach(b => b.onclick = async () => {
            catalogTag = chosenTags.filter(tag => tag !== b.dataset.removeTag).join(",");
            await showPage(1);
        });
        filterSelect("#catalog-pegi", catalogPegi, v => catalogPegi = v);
    }

    // Games not out yet: "Pré-reserva" on the cover, release date next to the platform
    const grid = cardGrid();
    data.groups.forEach(g => grid.appendChild(catalogCard(g)));
    wrap.appendChild(grid);
    wrap.appendChild(pagination(data.page, data.pages, showPage));
    return wrap;
}

// A catalogue card; games not out yet: "Pré-reserva" on the cover and the release date under the name
function catalogCard(g) {
    if (!g.is_preorder) return makeCard(g, { again: catalogCard });
    return makeCard(g, {
        coverBadge: `<span class="badge badge-pre discount-badge">${t("preorder")}</span>`,
        extraLine: `<span class="text-body-secondary">${icon("calendar", 14)} ${esc(releaseLabel(g.release_date, g.date_is_estimate))}</span>`,
        again: catalogCard,
    });
}

const FRONT_TABS = {
    discounts: {
        // Real discounts need 30 days of history; until there are some, show the biggest
        // price gaps between stores (clearly labelled as a comparison, not a discount)
        // Only the top 12 are loaded, so the platform filter is applied by the server
        // (filtering 12 games here could leave almost nothing)
        platformAware: true,
        load: async platform => {
            const query = platform ? `?platform=${encodeURIComponent(platform)}` : "";
            const discounts = await fetch(`/api/discounts/featured${query}`).then(r => r.json());
            if (discounts.length) return discounts;
            const deals = await fetch(`/api/deals${query}`).then(r => r.json());
            return deals.map(d => ({ ...d, isStoreDeal: true }));
        },
        render: renderDiscounts,
        empty: "empty_discounts",
    },
    preorders: { url: "/api/preorders", render: renderPreorders, empty: "empty_preorders", merge: true },
    releases: { url: "/api/releases", render: renderReleases, empty: "empty_releases", whole: true },
    catalog: catalogTab(false, "empty_catalog"),
    special: catalogTab(true, "empty_special"),
    hardware: catalogTab(false, "empty_hardware", true),
    market: {
        platformAware: true,
        paged: true,
        load: platform => {
            const page = pageFromUrl;
            pageFromUrl = 1;    // only for the first load
            return loadMarketPage(platform, page);
        },
        render: renderMarket,
        empty: "empty_market",
    },
};
const frontData = {};      // tab → data, loaded once per visit
const SHOW_STEP = 48;      // items drawn at a time on the long tabs ("Mostrar mais" for the next ones)
const frontShown = {};     // tab → how many are drawn now
const frontDataPlatform = {};   // tab → platform its data was loaded for (platform-aware tabs)
// Open tab: /?tab=releases if given (shareable links), else the visitor's last choice (one since removed, as the
// wishlist tab: the first; ?tab=wishlist links go to /wishlist, web.py)
let frontTab = FRONT_TABS[saved("frontTab")] ? saved("frontTab") : "discounts";
const tabFromUrl = new URLSearchParams(location.search).get("tab");
if (FRONT_TABS[tabFromUrl]) frontTab = tabFromUrl;

// Month and weekday names in the visitor's language
const monthName = d => d.toLocaleDateString(LOCALE, { month: "long" });
const weekdayName = d => d.toLocaleDateString(LOCALE, { weekday: "short" }).replace(".", "");


// Keep the address bar in step with what's on screen (/browse?q=… or /browse?tab=…), and remember it
// for this browser tab so the game page's back button returns exactly here
function setPageUrl(url) {
    history.replaceState(null, "", url);
    save("lastListPage", url, "sessionStorage");
}

async function selectFrontTab(tab) {
    frontTab = tab;
    frontShown[tab] = SHOW_STEP;
    save("frontTab", tab);
    document.querySelectorAll("[data-tab]").forEach(b => {
        b.classList.toggle("active", b.dataset.tab === tab);
        b.setAttribute("aria-selected", b.dataset.tab === tab);
        // the tab row scrolls sideways on a phone: keep the chosen tab in view
        if (b.dataset.tab === tab) b.scrollIntoView({ block: "nearest", inline: "nearest" });
    });

    const config = FRONT_TABS[tab];
    const platform = document.getElementById("consoleFilter").value;
    const stale = config.platformAware && frontDataPlatform[tab] !== platform;
    if (!frontData[tab] || stale) {
        document.getElementById("front-content").innerHTML = "";
        document.getElementById("front-empty").classList.add("d-none");
        document.getElementById("front-loading").classList.remove("d-none");
        try {
            if (config.load) {
                frontData[tab] = await config.load(platform);
                frontDataPlatform[tab] = platform;
            } else {
                const url = typeof config.url === "function" ? config.url() : config.url;
                frontData[tab] = await fetch(url).then(r => r.json());
            }
        } catch (e) {
            console.error("Erro a carregar", tab, e);
            frontData[tab] = [];
        }
        document.getElementById("front-loading").classList.add("d-none");
        if (tab !== frontTab) return;   // the visitor switched tabs while this was loading
    }

    // Address bar: /?tab=… (+ &page=… on catalogue pages), not while a search is on screen
    if (!document.getElementById("q").value.trim()) {
        // page and store filter only belong to the catalogue tabs
        setPageUrl(listUrl({ tab }, config.paged ? frontData[tab]?.page || 1 : 1));
    }
    renderFront();
}

// The platform filter applies to the front page too
function renderFront() {
    const config = FRONT_TABS[frontTab];
    if (!document.getElementById("q").value.trim()) frontSectionHead();
    const content = document.getElementById("front-content");
    const empty = document.getElementById("front-empty");
    content.innerHTML = "";

    // Catalogue tabs: one page of results, already filtered by platform on the server
    if (config.paged) {
        const data = frontData[frontTab];
        const hasGroups = Boolean(data?.groups?.length);
        // nothing with the chosen filters: keep them on screen so they can be changed
        // (the Used tab has only its type: the catalogue's filters don't apply to it)
        const filtered = frontTab === "market" ? Boolean(marketKind) : extraFilters().some(([, value]) => value);
        if (hasGroups || filtered) content.appendChild(config.render(data));
        empty.textContent = t(filtered ? "empty_filtered" : config.empty);
        empty.classList.toggle("d-none", hasGroups);
        return;
    }

    const selected = document.getElementById("consoleFilter").value;
    let items = (frontData[frontTab] || []).filter(i => !selected || (i.console || i.platform) === selected);
    if (config.merge) items = mergePlatforms(items);

    // Lançamentos draws all of them its own way (most anticipated, calendar)
    if (config.whole) {
        if (items.length) content.appendChild(config.render(items));
        empty.textContent = selected && frontData[frontTab]?.length ? t("empty_platform") : t(config.empty);
        empty.classList.toggle("d-none", items.length > 0);
        return;
    }

    // ~540 pre-orders at once made the page 65,000 px tall on a phone: SHOW_STEP at a time
    const shown = frontShown[frontTab] || SHOW_STEP;
    if (items.length) content.appendChild(config.render(items.slice(0, shown)));
    if (items.length > shown) {
        const more = document.createElement("button");
        more.type = "button";
        more.className = "btn btn-secondary d-block mx-auto mt-3 show-more";
        more.textContent = t("show_more", { count: items.length - shown });
        more.onclick = () => {
            frontShown[frontTab] = shown + SHOW_STEP;
            renderFront();
            content.querySelector(".show-more")?.focus();     // keyboard users carry on from here
        };
        content.appendChild(more);
    }

    empty.textContent = selected && frontData[frontTab]?.length ? t("empty_platform") : t(FRONT_TABS[frontTab].empty);
    empty.classList.toggle("d-none", items.length > 0);
}

function cardGrid() {
    const grid = document.createElement("div");
    grid.className = "row row-cols-2 row-cols-md-3 row-cols-lg-4 card-grid";
    return grid;
}

// ---------------------------------------------------------------------------
// Back-in-stock alerts for the wishlist
// The server flags offers that went from sold out to in stock recently (restocked_at);
// dismissed alerts are remembered per restock, so a later restock alerts again.
// ---------------------------------------------------------------------------

function restockKey(o) {
    return `${o.offer_id}@${o.restocked_at}`;
}

function dismissedRestocks() {
    return new Set(savedJSON("dismissedRestocks", []));
}

async function loadRestockAlerts() {
    if (!wishedIds().length) return;
    try {
        const groups = await loadWishlist();
        const dismissed = dismissedRestocks();
        const alerts = groups.flatMap(g => g.offers
            .filter(o => o.restocked_at && !dismissed.has(restockKey(o)))
            .map(o => ({ group: g, offer: o })));
        renderRestockAlerts(alerts);
    } catch (e) {
        console.error("Erro a verificar stock da lista de desejos:", e);
    }
}

function renderRestockAlerts(alerts) {
    const box = document.getElementById("alerts");
    if (!alerts.length) { box.innerHTML = ""; return; }

    const items = alerts.map(({ group, offer }) => `
        <li class="d-flex flex-wrap align-items-center gap-2 py-1">
            <a href="/game/${group.game_id}" class="fw-semibold link-body-emphasis">${esc(localName(group))}</a>
            <span class="text-body-secondary small">${esc(group.platform_name)}</span>
            <span>· ${esc(storeName(offer.store))} · <strong>${eur.format(offer.price)}</strong></span>
            <a href="${esc(offer.url)}" target="_blank" rel="noopener" class="btn btn-sm btn-success py-0">${t("view_in_store")}</a>
        </li>`).join("");

    box.innerHTML = `
        <div class="alert alert-warning alert-dismissible mb-4" role="status">
            <div class="fw-semibold mb-1">${icon("bell", 16)} ${alerts.length === 1 ? t("restock_one") : t("restock_many", { count: alerts.length })}</div>
            <ul class="list-unstyled mb-0">${items}</ul>
            <button type="button" class="btn-close" aria-label="${t("dismiss")}"></button>
        </div>`;

    box.querySelector(".btn-close").onclick = () => {
        const dismissed = dismissedRestocks();
        alerts.forEach(({ offer }) => dismissed.add(restockKey(offer)));
        save("dismissedRestocks", [...dismissed]);
        box.innerHTML = "";
    };
}

// Biggest real discounts (from our own price history, never the store's crossed-out price),
// or, while there are none yet, the biggest price gaps between stores
function renderDiscounts(offers) {
    // (while there are no real discounts, the section's line says these are gaps between stores)
    const wrap = document.createElement("div");
    const storeDeals = offers[0]?.isStoreDeal;
    const grid = cardGrid();
    // o.offers: this store's offer plus the other stores' prices, each shown as a button; the same game's
    // discount on another platform is a chip of the same card, with its own badge
    const groups = offers.map(o => ({ name: o.name, name_en: o.name_en, cover: o.cover, console: o.platform,
                                      platform_name: o.platform_name, game_id: o.game_id, edition_id: o.edition_id,
                                      same: o.same, deal: o, offers: o.offers || [o] }));
    const make = group => {
        const o = group.deal;
        return makeCard(group, {
            again: make,
            coverBadge: storeDeals
                ? `<span class="badge badge-save discount-badge" title="${esc(t("vs_other_stores_hint", { percent: o.savings_percent }))}">${
                    t("vs_other_stores", { saving: eur.format(o.savings ?? (o.next_price - o.price)) })}</span>`
                : `<span class="badge text-bg-danger discount-badge">-${o.discount_percent}%</span>`,
        });
    };
    mergePlatforms(groups).forEach(g => grid.appendChild(make(g)));
    wrap.appendChild(grid);
    return wrap;
}

function renderPreorders(groups) {
    const grid = cardGrid();
    // each platform's own date (they can differ)
    const make = g => makeCard(g, {
        coverBadge: `<span class="badge badge-pre discount-badge">${t("preorder")}</span>`,
        extraLine: `${icon("calendar", 14)} ${esc(releaseLabel(g.release_date, g.date_is_estimate))}`,
        again: make,
    });
    groups.forEach(g => grid.appendChild(make(g)));
    return grid;
}

// Lançamentos (user, 2026-10-14): two rows of the most anticipated games, then a month calendar where
// a day shows the games out that day. "31/12" estimates are a choice of their own under the calendar.
const ANTICIPATED = 8;              // games in the most anticipated slider
let releaseMonth = null;            // the calendar's month (a Date on its 1st)
let releaseDay = null;              // "2026-10-15", or "tba"

function renderReleases(groups) {
    const wrap = document.createElement("div");
    const dated = groups.filter(g => !g.date_is_estimate);
    const estimated = groups.filter(g => g.date_is_estimate);
    const byDay = {};
    dated.forEach(g => (byDay[g.release_date] ||= []).push(g));
    const days = Object.keys(byDay).sort();
    const today = isoDay(new Date());

    const top = mostAnticipated(groups, ANTICIPATED);
    clearInterval(slideTimer);
    if (top.length) wrap.appendChild(anticipatedSlider(top));

    // the day shown: the one picked, else today or the next day with releases
    if (releaseDay !== "tba" && !byDay[releaseDay]) releaseDay = days.find(d => d >= today) || (estimated.length ? "tba" : null);
    if (!releaseMonth) releaseMonth = monthStart(releaseDay && releaseDay !== "tba" ? parseDay(releaseDay) : new Date());
    const first = monthStart(new Date());
    const last = days.length ? monthStart(parseDay(days[days.length - 1])) : first;

    // the calendar beside the day's games on a wide screen, above them on a phone (user, 2026-10-14: under the
    // cards it left a lot of empty space). Picking a day or a month draws only this again, not the slider
    // (user, 2026-10-15: it went back to its start)
    const layout = document.createElement("div");
    layout.className = "release-layout";
    wrap.appendChild(layout);
    const redraw = focus => {
        layout.replaceChildren(...calendarParts(byDay, days, estimated, first, last, redraw));
        document.querySelector(focus)?.focus();
    };
    layout.append(...calendarParts(byDay, days, estimated, first, last, redraw));
    return wrap;
}

// The release calendar's month and the chosen day's games: [calendar, day's games]; redraw(selector to focus)
function calendarParts(byDay, days, estimated, first, last, redraw) {
    const today = isoDay(new Date());
    const box = document.createElement("section");
    box.className = "release-calendar";
    box.setAttribute("aria-label", t("releases_calendar"));
    const monthDays = new Date(releaseMonth.getFullYear(), releaseMonth.getMonth() + 1, 0).getDate();
    // this month from this week on: the weeks already over were rows of greyed-out days
    const now = new Date();
    const thisMonth = releaseMonth.getTime() === monthStart(now).getTime();
    const from = thisMonth ? Math.max(1, now.getDate() - (now.getDay() + 6) % 7) : 1;
    const blanks = (new Date(releaseMonth.getFullYear(), releaseMonth.getMonth(), from).getDay() + 6) % 7;   // weeks start on Monday
    const cells = [];
    for (let i = 0; i < blanks; i++) cells.push(`<span></span>`);
    for (let d = from; d <= monthDays; d++) {
        const iso = isoDay(new Date(releaseMonth.getFullYear(), releaseMonth.getMonth(), d));
        const count = byDay[iso] ? mergePlatforms(byDay[iso]).length : 0;
        cells.push(`<button type="button" class="cal-day${iso === today ? " is-today" : ""}" data-day="${iso}"
            aria-pressed="${iso === releaseDay}" ${count ? "" : "disabled"}
            aria-label="${esc(`${parseDay(iso).toLocaleDateString(LOCALE, { day: "numeric", month: "long" })}: ${count === 1 ? t("releases_day_one") : t("releases_day_many", { count })}`)}">
            <span>${d}</span>${count ? `<small>${count}</small>` : ""}</button>`);
    }
    // "seg", "ter"... (pt-PT's short names are whole words); 1 Jan 2024 was a Monday
    const names = Array.from({ length: 7 }, (_, i) => weekdayName(new Date(2024, 0, 1 + i)).slice(0, 3));
    box.innerHTML = `
        <div class="d-flex align-items-center gap-2 mb-2">
            <h3 class="h5 mb-0 flex-grow-1 first-cap">${esc(monthName(releaseMonth))} ${releaseMonth.getFullYear()}</h3>
            <button type="button" class="btn btn-sm btn-secondary" data-month="-1" aria-label="${esc(t("releases_prev_month"))}"
                    ${releaseMonth <= first ? "disabled" : ""}>&lsaquo;</button>
            <button type="button" class="btn btn-sm btn-secondary" data-month="1" aria-label="${esc(t("releases_next_month"))}"
                    ${releaseMonth >= last ? "disabled" : ""}>&rsaquo;</button>
        </div>
        <div class="cal-grid" role="group" aria-label="${esc(monthName(releaseMonth))}">
            ${names.map(n => `<span class="cal-head" aria-hidden="true">${esc(n)}</span>`).join("")}${cells.join("")}
        </div>
        ${estimated.length ? `<button type="button" class="btn btn-sm btn-secondary mt-2" data-day="tba" aria-pressed="${releaseDay === "tba"}">
            ${esc(t("date_tba"))} (${mergePlatforms(estimated).length})</button>` : ""}`;
    box.querySelectorAll("[data-month]").forEach(b => b.onclick = () => {
        releaseMonth = new Date(releaseMonth.getFullYear(), releaseMonth.getMonth() + Number(b.dataset.month), 1);
        const inMonth = days.find(d => d.startsWith(isoDay(releaseMonth).slice(0, 7)));
        if (inMonth) releaseDay = inMonth;
        redraw(`.release-calendar [data-month="${b.dataset.month}"]:not([disabled])`);
    });
    box.querySelectorAll("[data-day]").forEach(b => b.onclick = () => {
        releaseDay = b.dataset.day;
        redraw(`.release-calendar [data-day="${releaseDay}"]`);
    });
    const dayBox = document.createElement("section");
    dayBox.className = "min-w-0";
    const chosen = releaseDay === "tba" ? estimated : byDay[releaseDay] || [];
    if (releaseDay) {
        const title = releaseDay === "tba" ? t("date_tba")
            : parseDay(releaseDay).toLocaleDateString(LOCALE, { weekday: "long", day: "numeric", month: "long" });
        const count = mergePlatforms(chosen).length;
        dayBox.setAttribute("aria-label", title);
        dayBox.insertAdjacentHTML("beforeend", `<h3 class="h5 mb-2 first-cap">${esc(title)}
            <span class="small fw-normal text-body-secondary">· ${esc(count === 1 ? t("releases_day_one") : t("releases_day_many", { count }))}</span></h3>`);
        const grid = cardGrid();
        grid.className = "row row-cols-2 row-cols-md-3 row-cols-xxl-4 card-grid";       // the calendar takes a column
        mergePlatforms(chosen).forEach(c => grid.appendChild(releaseCard(c, releaseDay === "tba")));
        dayBox.appendChild(grid);
    }
    return [box, dayBox];
}

// A release's card: the date under it where the list isn't one day's; its editions count
function releaseCard(group, withDate) {
    const make = g => makeCard(g, {
        extraLine: [withDate ? `${icon("calendar", 14)} ${esc(releaseLabel(g.release_date, g.date_is_estimate))}` : "",
                    g.editions > 1 ? esc(t("editions_count", { count: g.editions })) : ""].filter(Boolean).join(" · "),
        again: make,
    });
    return make(group);
}

const monthStart = d => new Date(d.getFullYear(), d.getMonth(), 1);

function showFront(show) {
    document.getElementById("front").classList.toggle("d-none", !show);
    document.getElementById("home-btn").classList.toggle("d-none", show);
}

// Clear the search and show the front page tabs again
function goHome() {
    document.getElementById("q").value = "";
    search();
    window.scrollTo({ top: 0 });
}

// A section's tab also leaves a search (the tabs stay on screen while results are shown)
document.querySelectorAll("[data-tab]").forEach(b => b.addEventListener("click", async () => {
    if (document.getElementById("q").value.trim()) {
        document.getElementById("q").value = "";
        await search();
    }
    selectFrontTab(b.dataset.tab);
}));

let isSearching = false;

// Search: editions in stock whose title has every word, 48 per page, with the same store
// filter, sort and page buttons as the catalogue (served by /api/games/catalog?q=…)
async function search(page = 1) {
    const query = document.getElementById("q").value.trim();
    if (isSearching) return;

    // Empty search: back to the front page with the featured discounts
    if (!query) {
        hasSearched = false;
        currentData = null;
        document.getElementById("results").innerHTML = "";
        document.getElementById("empty").classList.add("d-none");
        setPageUrl(listUrl({ tab: frontTab }));
        showFront(true);
        frontSectionHead();
        return;
    }

    isSearching = true;
    showFront(false);
    setSectionHead(t("search_title", { q: query }));

    document.getElementById("loading").classList.remove("d-none");
    document.getElementById("empty").classList.add("d-none");
    document.getElementById("results").innerHTML = "";

    setPageUrl(listUrl({ q: query }, page));

    try {
        const params = catalogParams(page, document.getElementById("consoleFilter").value, { q: query });
        const data = await fetch(`/api/games/catalog?${params}`).then(r => r.json());
        currentData = { ...data, query };
        hasSearched = true;
        setSectionHead(t("search_title", { q: query }), t("search_results", { count: data.total }));
        renderSearch();
        if (page > 1) document.getElementById("results").scrollIntoView({ block: "start" });
    } catch (err) {
        console.error("Erro na pesquisa:", err);
    }

    document.getElementById("loading").classList.add("d-none");
    isSearching = false;
}

function renderSearch() {
    const container = document.getElementById("results");
    container.innerHTML = "";
    const found = currentData?.total > 0;
    // nothing at all for these words: "no games found"; nothing at one store / in one category: keep the filters visible
    const filtered = extraFilters().some(([, value]) => value);
    document.getElementById("empty").classList.toggle("d-none", found || filtered);
    if (found || filtered) container.appendChild(renderCatalog(currentData, p => search(p)));
}

document.getElementById("consoleFilter").addEventListener("change", () => {
    if (hasSearched) return search(1);
    // Platform-aware tabs ask the server again; the others filter what they already have
    if (FRONT_TABS[frontTab].platformAware) return selectFrontTab(frontTab);
    renderFront();
    setPageUrl(listUrl({ tab: frontTab }));
});

// Platforms, store names, categories and tags come from the API, so new ones appear without editing this page
async function loadFilters() {
    try {
        const [platforms, storeList, genreList, tagList] = await Promise.all([
            fetch("/api/platforms").then(r => r.json()),
            fetch("/api/stores").then(r => r.json()),
            fetch("/api/genres").then(r => r.json()),
            fetch("/api/tags").then(r => r.json()),
        ]);
        genres = genreList;
        tags = tagList;
        const select = document.getElementById("consoleFilter");
        platforms.forEach(p => select.add(new Option(p.name, p.code)));
        // /?…&platform=PS5: the platform the address names, when it's one of ours
        const fromUrl = startParams.get("platform");
        if (platforms.some(p => p.code === fromUrl)) select.value = fromUrl;
        renderPlatformPicker(platforms);
        storeList.forEach(s => stores[s.slug] = s);
        renderStoreStatus(storeList);
    } catch (e) {
        console.error("Erro a carregar filtros:", e);
    }
}

// The platform filter: the current platforms as chips ("Todas" first), the older ones in an "Outras"
// list; both set #consoleFilter, which the rest of the page reads
const MAIN_PLATFORMS = ["PS5", "PS4", "Switch2", "Switch", "XboxSeries", "XboxOne", "PC"];

function renderPlatformPicker(platforms) {
    const filter = document.getElementById("consoleFilter");
    const main = MAIN_PLATFORMS.map(code => platforms.find(p => p.code === code)).filter(Boolean);
    const others = platforms.filter(p => !MAIN_PLATFORMS.includes(p.code));
    const chips = document.getElementById("platform-chips");
    chips.innerHTML = [{ code: "", name: t("all_short") }, ...main].map(p => `
        <button type="button" class="chip-btn" data-platform="${esc(p.code)}" title="${esc(p.name)}"
            aria-pressed="false">${esc(p.code ? PLATFORM_SHORT[p.code] || p.name : p.name)}</button>`).join("");
    const more = document.getElementById("more-platforms");
    more.innerHTML = `<option value="">${esc(t("more_platforms"))}</option>`
        + others.map(p => `<option value="${esc(p.code)}">${esc(p.name)}</option>`).join("");
    more.classList.toggle("d-none", !others.length);

    const choose = code => {
        filter.value = code;
        filter.dispatchEvent(new Event("change"));
        markPlatform();
    };
    chips.querySelectorAll("[data-platform]").forEach(b => b.onclick = () => choose(b.dataset.platform));
    more.onchange = () => choose(more.value);
    markPlatform();
}

function markPlatform() {
    const code = document.getElementById("consoleFilter").value;
    document.querySelectorAll("#platform-chips [data-platform]").forEach(b => b.setAttribute("aria-pressed", b.dataset.platform === code));
    const more = document.getElementById("more-platforms");
    const isOther = Boolean(code) && !MAIN_PLATFORMS.includes(code);
    more.value = isOther ? code : "";
    more.classList.toggle("chosen", isOther);
}

// The title over the cards: the open section and a line about it, or the search
function setSectionHead(title, sub = "") {
    document.getElementById("section-title").textContent = title;
    document.getElementById("section-sub").textContent = sub;
}

function frontSectionHead() {
    const storeDeals = frontTab === "discounts" && frontData.discounts?.[0]?.isStoreDeal;
    const active = Object.values(stores).filter(s => s.is_active !== false).length;
    setSectionHead(t(`tab_${frontTab}`), t(storeDeals ? "sub_store_deals" : `sub_${frontTab}`, { stores: active }));
}

function timeAgo(iso) {
    const hours = (Date.now() - new Date(iso)) / 3600000;
    if (hours < 1) return t("ago_less_hour");
    if (hours < 48) return t("ago_hours", { count: Math.floor(hours) });
    return t("ago_days", { count: Math.floor(hours / 24) });
}

// "Preços atualizados: CSTech há 3 h · Mega Mania há 3 h · (warning icon) Press Start: falhou há 1 h"
function renderStoreStatus(storeList) {
    const parts = storeList.map(s => {
        const problem = s.last_status === "failed" ? t("status_failed")
                      : s.last_status === "warning" ? t("status_warning")
                      : s.is_stale ? t("status_stale") : null;
        const when = s.last_updated ? t("updated_ago", { ago: timeAgo(s.last_updated) }) : t("never_updated");
        if (!problem) return `<span>${esc(s.name)} ${when}</span>`;
        return `<span class="text-warning-emphasis" title="${esc(s.last_error || "")}">${icon("alert", 14)} ${esc(s.name)}: ${problem} (${when})</span>`;
    });
    document.getElementById("store-status").innerHTML =
        `${t("status_intro")} ${parts.join(" · ")}`;
}

// The user's collection and wishlist, to mark the cards (app/services/collection_service.py).
// Favourites were folded into the wishlist; ones an old browser still keeps ("favoriteEditions",
// from before accounts) go onto the wishlist at log-in.
const BROWSER_FAVORITES = "favoriteEditions";

async function loadCollectionIds() {
    collectionIds = {};
    if (!currentUser) return;
    const fromBrowser = savedJSON(BROWSER_FAVORITES, []).filter(Number.isInteger);
    if (fromBrowser.length && (await api("/api/collection/import", { body: { ids: fromBrowser } })).ok) {
        forget(BROWSER_FAVORITES);
    }
    collectionIds = await fetch("/api/collection/editions").then(r => r.ok ? r.json() : {}).catch(() => ({}));
}

// The wished edition ids (numbers)
function wishedIds() {
    return Object.entries(collectionIds).filter(([, mine]) => mine.wishlist).map(([id]) => Number(id));
}

// The wished editions with their offers (cards); the API takes 200 at a time, /collection lists them all
function loadWishlist() {
    return fetch(`/api/games/editions?ids=${wishedIds().slice(0, 200).join(",")}`).then(r => r.json());
}

// The card's round button (user, 2026-10-13: one clear sign, no emoji): a tick on blue when the user owns the
// edition, a gold star when they want it, else an empty star; the state is also said in words for screen readers
function starButton(group) {
    const mine = collectionIds[group.edition_id] || {};
    if (mine.owned) return `<span class="fav-owned">${icon("check", 15)}</span><span class="visually-hidden">${esc(t("card_state_owned"))}</span>`;
    if (mine.wishlist) return `<span class="fav-wished">${icon("star", 15, { filled: true })}</span><span class="visually-hidden">${esc(t("card_state_wish"))}</span>`;
    return icon("star", 15);
}

// The star opens a menu for the card's edition: Quero, Tenho, each on / off, and Vender
// (the sell form on this edition, without going through the game page).
// One menu open at a time; Esc, a click elsewhere or Tab closes it
let cardMenu = null;    // {menu, button, group}

function toggleCardMenu(button, group, fill = () => fillCardMenu("wishlist")) {
    const wasOpen = cardMenu?.button === button;
    closeCardMenu();
    if (wasOpen) return;
    const menu = document.createElement("div");
    menu.className = `dropdown-menu show card-menu shadow${fill === fillAdminMenu ? " admin-menu" : ""}`;
    menu.setAttribute("role", "menu");
    button.after(menu);
    button.setAttribute("aria-expanded", "true");
    cardMenu = { menu, button, group };
    fill();
}

// --- Staff: the "..." menu at a card's bottom right (user, 2026-10-13): pick two cards, merge them in a window ---
// The first card picked waits in this tab (sessionStorage) while the moderator browses or searches for the second
const MERGE_PICK = "merge-pick";

function isStaff() {
    return ["moderator", "admin"].includes(currentUser?.role);
}

function mergePick() {
    return savedJSON(MERGE_PICK, {}, "sessionStorage");
}

function fillAdminMenu() {
    const { menu, group } = cardMenu;
    const picked = mergePick();
    const label = picked.edition_id === group.edition_id ? "merge_unpick" : picked.edition_id ? "merge_with_picked" : "merge_pick";
    menu.innerHTML = `
        <button type="button" class="dropdown-item" role="menuitem" data-pick>${esc(t(label))}</button>
        <a class="dropdown-item" role="menuitem" href="/admin">${esc(t("mod_title"))}</a>`;
    menu.querySelector("[data-pick]").onclick = () => {
        closeCardMenu();
        pickForMerge(group);
    };
    menu.querySelector("[data-pick]").focus();
}

// What the merge window shows of a card (the platform it shows now)
function mergeCard(group) {
    const [title, edition] = splitEdition(localName(group));
    return { edition_id: group.edition_id, game_id: group.game_id, title, edition: edition || "Standard",
             platform: group.platform_name, console: group.console,
             cover: group.cover || group.offers?.[0]?.image || group.image || "" };
}

function pickForMerge(group) {
    const picked = mergePick();
    if (picked.edition_id === group.edition_id) forget(MERGE_PICK, "sessionStorage");
    else if (!picked.edition_id) save(MERGE_PICK, mergeCard(group), "sessionStorage");
    else return openMerge(picked, mergeCard(group));
    showMergeBar();
}

// The picked card outlined, and a bar at the bottom saying which it is (with "Cancelar")
function showMergeBar() {
    document.getElementById("merge-bar")?.remove();
    document.querySelectorAll(".game-card.merge-picked").forEach(c => c.classList.remove("merge-picked"));
    const picked = mergePick();
    if (!picked.edition_id || !isStaff()) return;
    document.querySelectorAll(`.game-card[data-edition-id="${picked.edition_id}"]`).forEach(c => c.classList.add("merge-picked"));
    const bar = document.createElement("div");
    bar.id = "merge-bar";
    bar.className = "merge-bar shadow";
    bar.setAttribute("role", "status");
    bar.innerHTML = `<span class="small">${esc(t("merge_bar", { name: `${picked.title} · ${picked.edition} (${picked.platform || ""})` }))}</span>
        <button type="button" class="btn btn-sm btn-secondary">${esc(t("merge_cancel"))}</button>`;
    bar.querySelector("button").onclick = () => {
        forget(MERGE_PICK, "sessionStorage");
        showMergeBar();
    };
    document.body.appendChild(bar);
}

// The window: both cards, whose name stays and which edition stays (match_service.merge_cards)
function openMerge(a, b) {
    const dialog = document.getElementById("merge-dialog");
    const body = dialog.querySelector("[data-body]");
    const side = c => `
        <div class="merge-side">
            <img src="${esc(c.cover)}" class="${coverClass(c.cover)}" alt="">
            <div class="small min-w-0"><strong>${esc(c.title)}</strong><div>${esc(c.edition)}</div>
                <div class="text-body-secondary">${esc(c.platform || "")} · #${c.game_id}</div></div>
        </div>`;
    const radios = (name, options) => options.map(([value, label], i) => `
        <div class="form-check small"><input class="form-check-input" type="radio" name="${name}" id="${name}-${i}" value="${value}"
            ${i === 0 ? "checked" : ""}><label class="form-check-label" for="${name}-${i}">${esc(label)}</label></div>`).join("");
    const sameGame = a.game_id === b.game_id;
    body.innerHTML = `
        <div class="merge-pair">${side(a)}<span class="merge-plus" aria-hidden="true">+</span>${side(b)}</div>
        ${a.console !== b.console ? `<p class="small text-danger mt-3 mb-0">${esc(t("merge_other_platform"))}</p>` : `
            ${sameGame ? "" : `<fieldset class="mt-3"><legend class="small fw-semibold mb-1">${esc(t("merge_keep_name"))}</legend>
                ${radios("merge-name", [[a.game_id, a.title], [b.game_id, b.title]])}</fieldset>`}
            <fieldset class="mt-2"><legend class="small fw-semibold mb-1">${esc(t("merge_keep_edition"))}</legend>
                ${radios("merge-edition", [[a.edition_id, `${a.edition} · ${a.title}`], [b.edition_id, `${b.edition} · ${b.title}`]])}</fieldset>
            <p class="small text-body-secondary mt-2 mb-2">${esc(t("merge_explain"))}</p>
            <button type="button" class="btn btn-danger btn-sm" data-go>${esc(t("merge_go"))}</button>`}
        <div class="small mt-2" data-message role="status"></div>`;
    const go = body.querySelector("[data-go]");
    if (go) go.onclick = async () => {
        const keep = Number(body.querySelector("[name=merge-edition]:checked").value);
        const other = keep === a.edition_id ? b.edition_id : a.edition_id;
        const name = body.querySelector("[name=merge-name]:checked");
        go.disabled = true;
        const { ok, data: answer } = await api("/api/mod/merge-cards", {
            body: { keep_edition_id: keep, other_edition_id: other, ...(name ? { title_game_id: Number(name.value) } : {}) } });
        go.disabled = false;
        const message = body.querySelector("[data-message]");
        message.className = `small mt-2 ${ok ? "text-success" : "text-danger"}`;
        message.textContent = ok ? t("merge_done") : t(`error_${answer?.error || "unknown"}`);
        if (ok) {
            forget(MERGE_PICK, "sessionStorage");
            setTimeout(() => location.reload(), 900);
        }
    };
    dialog.querySelectorAll("[data-close]").forEach(button => button.onclick = () => dialog.close());
    dialog.onclick = event => { if (event.target === dialog) dialog.close(); };
    dialog.showModal();
    go?.focus();
}

function fillCardMenu(focusKind) {
    const { menu, group } = cardMenu;
    const mine = collectionIds[group.edition_id] || {};
    // the icon says whether it's on: a gold filled star when wished, blue books (Coleção's icon) when owned,
    // grey when not
    const items = [["wishlist", "star", t("collection_add_wishlist"), Boolean(mine.wishlist)],
                   ["owned", "library", t("collection_add_owned"), Boolean(mine.owned)]];
    menu.innerHTML = items.map(([kind, name, label, on]) => `
        <button type="button" class="dropdown-item" role="menuitemcheckbox" aria-checked="${on}" data-kind="${kind}">
            <span class="menu-icon menu-icon-${kind}">${icon(name, 16, { filled: on && kind === "wishlist" })}</span>${esc(label)}</button>`).join("") + `
        <hr class="dropdown-divider">
        <a class="dropdown-item" role="menuitem" href="/sell?game_id=${group.game_id}&edition_id=${group.edition_id}">
            <span class="menu-icon">${icon("tag", 16)}</span>${esc(t("card_sell"))}</a>`;
    menu.querySelectorAll("[data-kind]").forEach(b => b.onclick = () => toggleCardItem(group, b.dataset.kind));
    menu.querySelector(`[data-kind="${focusKind}"]`).focus();
}

function closeCardMenu(focusButton = false) {
    if (!cardMenu) return;
    cardMenu.menu.remove();
    cardMenu.button.setAttribute("aria-expanded", "false");
    if (focusButton) cardMenu.button.focus();
    cardMenu = null;
}

document.addEventListener("click", e => {
    if (cardMenu && !cardMenu.menu.contains(e.target) && !cardMenu.button.contains(e.target)) closeCardMenu();
});

document.addEventListener("keydown", e => {
    if (!cardMenu) return;
    if (e.key === "Escape") return closeCardMenu(true);
    if (e.key === "Tab") return closeCardMenu();
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const items = [...cardMenu.menu.querySelectorAll(".dropdown-item")];
        const next = items.indexOf(document.activeElement) + (e.key === "ArrowDown" ? 1 : -1);
        items[(next + items.length) % items.length].focus();
    }
});

// Logged out, every entry asks to log in first (the wishlist and the collection belong to an account)
async function toggleCardItem(group, kind) {
    if (!currentUser) return location.assign(`/account?next=${encodeURIComponent(location.pathname + location.search)}`);
    const id = group.edition_id;
    const item = (collectionIds[id] || {})[kind];
    const { ok } = item
        ? await api(`/api/collection/${item}`, { method: "DELETE" })
        : await api("/api/collection", { body: { edition_id: id, kind } });
    if (!ok) return;
    await loadCollectionIds();      // "Tenho" also takes it off the wishlist
    // the same edition can be on more than one card
    document.querySelectorAll(`.fav-btn[data-edition="${id}"]`).forEach(b => b.innerHTML = starButton(group));
    if (cardMenu) fillCardMenu(kind);
}

applyI18n();

// Who's logged in first (their wishlist marks the stars), then the filters and the page;
// /?q=zelda opens with that search, so searches can be bookmarked or shared
(async () => {
    await renderAccountArea();
    showMergeBar();
    await loadCollectionIds();
    await loadFilters();
    const params = new URLSearchParams(location.search);
    const q = params.get("q");
    if (q) {
        document.getElementById("q").value = q;
        search(Number(params.get("page")) || 1);
    }
    // after loadFilters, so the cards show store names
    selectFrontTab(frontTab);
    loadRestockAlerts();
})();

// The header's home links and the search form (bound here: the page has no inline handlers)
document.querySelectorAll("[data-go-home]").forEach(el => el.addEventListener("click", event => {
    event.preventDefault();
    goHome();
}));
document.getElementById("search-form").addEventListener("submit", handleSearch);
