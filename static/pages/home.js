// The home page, at / (templates/home.html; user, 2026-10-15): the most anticipated games in the big slider
// (static/slider.js, as in Lançamentos), then a sideways row each of the latest releases, the biggest discounts and
// the historical lows; one platform filter for all of them, remembered in this browser. Each "Ver tudo" opens the
// list's tab on /browse. t(), eur: static/i18n.js; esc(), icon(), storeName(), mergePlatforms(): static/common.js
const HOME_PLATFORMS = ["PS5", "PS4", "Switch2", "Switch", "XboxSeries", "XboxOne", "PC"];
const ROW_SIZE = 20;                 // cards in a row
const SLIDES = 12;                   // games in the slider
let stores = {};                     // storeName(): "cstech" is "CSTech"
let platform = HOME_PLATFORMS.includes(saved("homePlatform")) ? saved("homePlatform") : "";
let upcoming = [], recent = [];      // every platform's; filtered here (the others ask the server per platform)

const json = url => fetch(url).then(r => r.ok ? r.json() : Promise.reject(new Error(`${url}: ${r.status}`)));
const query = params => new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null)).toString();
const forPlatform = list => list.filter(g => !platform || g.console === platform);
const bestOffer = g => (g.offers || []).filter(o => o.in_stock).sort((a, b) => a.price - b.price)[0] || null;
const shortName = g => PLATFORM_SHORT[g.console || g.platform] || g.platform_name;
const dayLabel = iso => parseDay(iso).toLocaleDateString(LOCALE, { day: "numeric", month: "short" }).replace(".", "");

// The platform chips: "Todas" and the current platforms (the older ones have almost no new games)
function renderPlatforms() {
    const box = document.getElementById("home-platforms");
    box.innerHTML = ["", ...HOME_PLATFORMS].map(code => `<button type="button" class="chip-btn" data-platform="${code}"
        aria-pressed="${code === platform}">${esc(code ? PLATFORM_SHORT[code] : t("all_short"))}</button>`).join("");
    box.querySelectorAll("[data-platform]").forEach(b => b.onclick = () => {
        platform = b.dataset.platform;
        save("homePlatform", platform);
        box.querySelectorAll("[data-platform]").forEach(c => c.setAttribute("aria-pressed", c === b));
        draw();
    });
}

// One card: the list's badge on the cover, the platforms (all of a game's, one card per game), name, best price
function card(g, badge) {
    const offer = bestOffer(g);
    const price = offer?.price ?? g.price;
    const store = offer ? offer.store : g.store;
    const picture = g.cover || offer?.image || g.image || "";
    const platforms = (platformsOf(g) || [g]).map(shortName).join(" · ");
    return `<a class="home-card" href="/game/${g.game_id}">
        <div class="cover"><img class="${coverClass(picture)}" src="${esc(picture)}" alt="" loading="lazy">${badge}</div>
        <div class="plat">${esc(platforms)}</div>
        <div class="name">${esc(localName(g) || g.title)}</div>
        ${price ? `<div class="price">${eur.format(price)}</div><div class="meta">${esc(g.why || storeName(store) || "")}</div>`
                : `<div class="meta">${esc(t("no_offers"))}</div>`}
    </a>`;
}

// A row: its title and line, "Ver tudo", and the cards scrolling sideways (arrows where there's a mouse)
function row(title, sub, href, cards) {
    const section = document.createElement("section");
    section.className = "mb-4";
    section.setAttribute("aria-label", title);
    section.innerHTML = `
        <div class="row-head"><div class="min-w-0"><h2>${esc(title)}</h2><div class="row-sub">${esc(sub)}</div></div>
            ${href ? `<a class="see-all" href="${href}">${esc(t("home_see_all"))} &rsaquo;</a>` : ""}</div>
        ${cards.length ? `<div class="rail-wrap">
            <button type="button" class="rail-btn prev" aria-label="${esc(t("home_row_prev"))}">&lsaquo;</button>
            <div class="rail">${cards.join("")}</div>
            <button type="button" class="rail-btn next" aria-label="${esc(t("home_row_next"))}">&rsaquo;</button>
        </div>` : `<p class="text-body-secondary small mb-0">${esc(t("home_row_empty"))}</p>`}`;
    const rail = section.querySelector(".rail");
    if (rail) {
        const prev = section.querySelector(".prev"), next = section.querySelector(".next");
        const ends = () => {
            prev.disabled = rail.scrollLeft <= 2;
            next.disabled = rail.scrollLeft + rail.clientWidth >= rail.scrollWidth - 2;
        };
        prev.onclick = () => rail.scrollBy({ left: -rail.clientWidth, behavior: "smooth" });
        next.onclick = () => rail.scrollBy({ left: rail.clientWidth, behavior: "smooth" });
        rail.addEventListener("scroll", ends, { passive: true });
        requestAnimationFrame(ends);
    }
    return section;
}

// The big slider: Lançamentos' (slider.js), with a link to that tab
function drawSlider() {
    clearInterval(slideTimer);
    slideIndex = 0;
    const box = document.getElementById("home-slider");
    const top = mostAnticipated(forPlatform(upcoming), SLIDES);
    box.replaceChildren();
    if (!top.length) return;
    const slider = anticipatedSlider(top);
    slider.querySelector("h3").parentElement.insertAdjacentHTML("beforeend",
        `<a class="see-all small ms-auto" href="/browse?${query({ tab: "releases", platform })}">${esc(t("home_see_all"))} &rsaquo;</a>`);
    box.appendChild(slider);
}

// Real discounts start once there are 30 days of prices; until then the biggest gaps between stores (as /browse)
async function savingRow() {
    const discounts = await json(`/api/discounts/featured?${query({ limit: ROW_SIZE, platform })}`);
    if (discounts.length) {
        return row(t("home_discounts"), t("home_discounts_sub"), `/browse?${query({ tab: "discounts", platform })}`,
                   mergePlatforms(discounts).map(d => card(d, `<span class="badge tag tag-sale">-${Math.round(d.discount_percent)}%</span>`)));
    }
    const deals = await json(`/api/deals?${query({ limit: ROW_SIZE, platform })}`);
    return row(t("home_discounts"), t("home_deals_sub"), `/browse?${query({ tab: "discounts", platform })}`,
               deals.map(d => card({ ...d, why: t("home_deal_next", { price: eur.format(d.next_price), store: storeName(d.next_store) }) },
                                   `<span class="badge tag tag-save">-${eur.format(d.savings)}</span>`)));
}

async function lowsRow() {
    const page = await json(`/api/games/catalog?${query({ tags: "historical_low", per_page: ROW_SIZE, sort: "price_desc", platform })}`);
    return row(t("home_lows"), t("home_lows_sub"), `/browse?${query({ tab: "catalog", tags: "historical_low", platform })}`,
               page.groups.map(g => card(g, `<span class="badge tag tag-low">${esc(t("home_low_badge"))}</span>`)));
}

function recentRow() {
    const cards = mergePlatforms(forPlatform(recent)).slice(0, ROW_SIZE)
        .map(g => card(g, `<span class="badge tag tag-new">${esc(dayLabel(g.release_date))}</span>`));
    return row(t("home_recent"), t("home_recent_sub"), null, cards);
}

let drawing = 0;         // a quicker platform choice wins over a slower one still loading
async function draw() {
    const mine = ++drawing;
    drawSlider();
    const rows = document.getElementById("home-rows");
    rows.setAttribute("aria-busy", "true");
    const settled = await Promise.allSettled([savingRow(), lowsRow()]);
    if (mine !== drawing) return;
    const [saving, lows] = settled.map(s => s.status === "fulfilled" ? s.value : null);
    rows.replaceChildren(...[recentRow(), saving, lows].filter(Boolean));
    rows.removeAttribute("aria-busy");
}

async function start() {
    applyI18n();
    renderAccountArea();
    renderPlatforms();
    try {
        const [storeList, up, latest] = await Promise.all([json("/api/stores"), json("/api/releases"), json("/api/releases/recent")]);
        storeList.forEach(s => stores[s.slug] = s);
        upcoming = up;
        recent = latest;
    } catch (e) {
        console.error("Erro a carregar a página inicial:", e);
    }
    draw();
}
start();
