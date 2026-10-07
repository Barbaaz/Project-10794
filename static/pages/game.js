// The game page (templates/game.html). A file, not inline: the site's CSP only runs scripts from files.
const GAME_ID = Number(document.body.dataset.gameId);
// t(), eur, LOCALE: static/i18n.js
const fmtDate = d => new Date(d).toLocaleDateString(LOCALE);
const fmtDateTime = d => new Date(d).toLocaleString(LOCALE, { dateStyle: "short", timeStyle: "short" });

let game, history, stores = {}, rangeDays = 90;
const charts = [];

function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function storeColor(slug) {
    const slot = stores[slug]?.color_slot || 6;
    return css(`--series-${Math.min(slot, 6)}`);
}

async function load() {
    try {
        const [g, h, s] = await Promise.all([
            fetch(`/api/games/${GAME_ID}`).then(r => r.ok ? r.json() : Promise.reject(r.status)),
            fetch(`/api/games/${GAME_ID}/prices?days=3650`).then(r => r.json()),
            fetch(`/api/stores`).then(r => r.json()),
        ]);
        game = g; history = h;
        s.forEach(store => stores[store.slug] = store);
        render();
    } catch (status) {
        document.getElementById("error").textContent =
            status === 404 ? t("game_not_found") : t("game_load_error");
        document.getElementById("error").classList.remove("d-none");
    }
    document.getElementById("loading").classList.add("d-none");
}

function render() {
    document.title = `${localName(game, "title")} (${game.platform}) · Game Price Tracker`;
    document.getElementById("title").textContent = localName(game, "title");
    document.getElementById("platform").textContent = game.platform_name;

    // Upcoming games: announced release date ("31/12" means only the year is known)
    if (game.release_date && new Date(game.release_date + "T23:59:59") >= new Date()) {
        const [y, m, d] = game.release_date.split("-");
        const release = document.getElementById("release");
        release.textContent = game.date_is_estimate ? t("release_tba", { year: y }) : t("release_on", { date: fmtDate(`${y}-${m}-${d}T12:00:00`) });
        release.classList.remove("d-none");
    }

    const cover = game.image || game.editions.flatMap(e => e.offers).find(o => o.image)?.image
        || (game.cover_image_id ? igdbImage(game.cover_image_id, "t_cover_big") : null);
    if (cover) document.getElementById("cover").src = cover;
    else document.getElementById("cover").classList.add("d-none");

    renderFacts();
    renderPriceSummary();
    renderAbout();

    const firstDate = history.flatMap(o => o.history).map(p => p.date).sort()[0];
    document.getElementById("history-note").textContent = firstDate
        ? t("tracked_since", { date: fmtDate(firstDate) })
        : "";

    const container = document.getElementById("editions");
    container.innerHTML = "";
    game.editions.forEach((edition, i) => container.appendChild(renderEdition(edition, i)));
    drawCharts();
    loadMarket();
    // players' reviews are of games; a console has none (core/hardware.py)
    const isGame = (game.kind || "game") === "game";
    document.getElementById("reviews").classList.toggle("d-none", !isGame);
    if (isGame) loadReviewsOnce();
    document.querySelector('#about [data-i18n="about"]').textContent = t(isGame ? "about" : "about_product");
    if (!isGame) {
        document.getElementById("sell-link").textContent = t("market_sell_this_product");
        document.getElementById("market-empty").textContent = t("market_empty_product");
    }
    fillCollectionButtons();

    document.getElementById("game").classList.remove("d-none");
}

// "Melhor preço agora: 26,99 € · Mega Mania [Ver na loja]": the cheapest new copy in stock of any
// edition (named when the game has several), above the fold on a phone
function renderPriceSummary() {
    const offers = game.editions.flatMap(e => e.offers.filter(o => o.in_stock && o.condition === "new").map(o => ({ ...o, edition: e })));
    const best = offers.sort((a, b) => a.price - b.price)[0];
    const box = document.getElementById("price-summary");
    if (!best) { box.innerHTML = ""; return; }
    const edition = game.editions.length > 1 ? ` · ${esc(localName(best.edition))}` : "";
    box.innerHTML = `
        <div class="d-flex flex-wrap align-items-center gap-2">
            <span class="fs-5">${t("best_price_now")} <strong>${eur.format(best.price)}</strong></span>
            <span class="text-body-secondary">${esc(storeName(best.store))}${edition}</span>
            <a href="${esc(best.url)}" target="_blank" rel="noopener" class="btn btn-sm btn-primary offer-link">${t("view_in_store")}</a>
            ${best.edition.at_historical_low ? `<span class="badge text-bg-success">${t("lowest_ever_now")}</span>` : ""}
        </div>`;
}

function igdbImage(id, size) {
    return `https://images.igdb.com/igdb/image/upload/${size}/${encodeURIComponent(id)}.jpg`;
}

// PEGI, genres and facts (publisher, developer, release, rating) from IGDB, with the
// stores' data sheet filling the gaps
function renderFacts() {
    const sd = game.store_details || {};
    if (game.pegi) {
        const pegi = document.getElementById("pegi");
        pegi.textContent = `PEGI ${game.pegi}`;
        pegi.classList.remove("d-none");
    }

    const genres = (game.genres || sd["Género"] || "").split(",").map(g => g.trim()).filter(Boolean);
    document.getElementById("genres").innerHTML =
        genres.map(g => `<span class="badge rounded-pill text-bg-secondary me-1">${esc(g)}</span>`).join("");

    const released = game.first_release_date;
    const facts = [
        [t("publisher"), game.publishers || sd["Editora"]],
        [t("developer"), game.developers || sd["Produtora"]],
        [t("released"), released && new Date(released + "T12:00:00") <= new Date() ? fmtDate(released + "T12:00:00") : null],
        [t("rating"), game.rating ? `${game.rating}/100 (IGDB)` : null],
        [t("time_to_beat"), timeToBeat()],
    ].filter(([, value]) => value);
    document.getElementById("facts").innerHTML =
        facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
}

// "História ~25 h · Com extras ~40 h · 100% ~60 h (IGDB, 31 jogadores)": IGDB players' times
function timeToBeat() {
    const hours = seconds => seconds ? `~${fmtNumber(Math.max(1, Math.round(seconds / 3600)))} h` : null;
    const parts = [["ttb_hastily", game.ttb_hastily], ["ttb_normally", game.ttb_normally], ["ttb_completely", game.ttb_completely]]
        .filter(([, s]) => s).map(([key, s]) => `${t(key)} ${hours(s)}`);
    return parts.length ? `${parts.join(" · ")} (${t("ttb_source", { count: game.ttb_count || 0 })})` : null;
}

// The store's Portuguese description of the standard edition if there is one; otherwise
// the longest store description; IGDB's English summary shown too (or on its own)
function renderAbout() {
    const parts = [];
    const storeText = aboutStoreText();

    const store = storeText && { text: storeText.text, label: t(LANG === "pt" ? "store_description" : "store_description_pt", { store: storeName(storeText.store) }) };
    const igdb = game.summary && { text: game.summary, label: t("igdb_summary") };
    const [main, extra] = LANG === "pt" ? [store || igdb, store && igdb] : [igdb || store, igdb && store];

    if (main) {
        parts.push(`${clampedText(main.text, 6)}<div class="small text-body-secondary mt-1">${esc(main.label)}</div>`);
    }
    if (extra) {
        parts.push(`<details class="mt-2"><summary class="small">${esc(extra.label)}</summary>
            <div class="mt-1">${clampedText(extra.text, 4)}</div></details>`);
    }

    // IGDB's screenshots; for games IGDB doesn't have, the stores' photos of the standard edition
    const shots = (game.screenshot_ids || []).map(id => ({ full: igdbImage(id, "t_1080p"), small: igdbImage(id, "t_screenshot_med") }));
    const standardPhotos = game.editions.find(e => e.name === "Standard")?.photos || [];
    const pictures = shots.length ? shots : standardPhotos.map(p => ({ full: p.url, small: p.url }));
    document.getElementById("screenshots").innerHTML = pictures.map(p => `
        <a href="${esc(p.full)}" target="_blank" rel="noopener">
            <img src="${esc(p.small)}" alt="${t("screenshot")}" loading="lazy"></a>`).join("");

    renderVideos();

    document.getElementById("about-text").innerHTML = parts.join("");
    document.getElementById("igdb-credit").classList.toggle("d-none", !game.igdb_id);
    const hasFacts = Boolean(document.getElementById("facts").children.length);
    document.getElementById("about").classList.toggle("d-none", !hasFacts && !parts.length && !pictures.length && !game.videos.length);
    bindClampToggles(document.getElementById("about"));
}

// IGDB's YouTube videos as thumbnails (i.ytimg.com); the player (youtube-nocookie) is only
// loaded on click, so opening the page doesn't load YouTube's player and its cookies
function renderVideos() {
    const videos = game.videos || [];
    document.getElementById("videos").classList.toggle("d-none", !videos.length);
    const player = document.getElementById("video-player");
    player.innerHTML = "";
    player.classList.add("d-none");

    const list = document.getElementById("video-list");
    list.innerHTML = videos.map(v => {
        const name = v.name || t("videos");
        return `<button type="button" class="video-thumb" data-video="${esc(v.id)}" title="${esc(name)}"
                    aria-label="${esc(t("play_video", { name }))}">
                <img src="https://i.ytimg.com/vi/${encodeURIComponent(v.id)}/mqdefault.jpg" alt="" loading="lazy" class="rounded">
                <span class="play" aria-hidden="true">▶</span>
                <span class="name">${esc(name)}</span></button>`;
    }).join("");
    list.querySelectorAll("[data-video]").forEach(btn => btn.onclick = () => {
        const id = encodeURIComponent(btn.dataset.video);
        player.innerHTML = `<iframe src="https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0"
            title="${esc(btn.title)}" allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
            allowfullscreen class="rounded"></iframe>`;
        player.classList.remove("d-none");
        player.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
}

// A store description about the game itself: the standard edition's, or a special edition's
// without its contents list ("Conteúdo da Collector's Edition: - ..." belongs to "O que inclui")
function aboutStoreText() {
    const standard = game.editions.find(e => e.name === "Standard");
    if (standard?.descriptions.length) return standard.descriptions[0];
    for (const d of game.editions.flatMap(e => e.descriptions)) {
        const text = withoutContents(d.text);
        if (text.length >= 150) return { ...d, text };
    }
    return null;
}

function withoutContents(text) {
    const lines = text.split("\n");
    const start = lines.findIndex(l => /conte[uú]do|inclui|includes|cont[eé]m/i.test(l));
    if (start < 0) return text;
    let end = start + 1;
    while (end < lines.length && /^\s*[-–•*·]/.test(lines[end])) end++;
    return [...lines.slice(0, start), ...lines.slice(end)].join("\n").trim();
}

// Long text shown on N lines with a "Ler mais" button
function clampedText(text, lines) {
    const long = text.length > lines * 90;
    const html = esc(text).replace(/\n/g, "<br>");
    return `<div class="clamped" style="--lines:${lines}">${html}</div>`
        + (long ? `<button type="button" class="btn btn-sm btn-secondary mt-1 clamp-toggle">${t("read_more")}</button>` : "");
}

function bindClampToggles(root) {
    root.querySelectorAll(".clamp-toggle").forEach(btn => btn.onclick = () => {
        const text = btn.previousElementSibling;
        const open = text.classList.toggle("open");
        btn.textContent = open ? t("read_less") : t("read_more");
    });
}

// "Conteúdo da Collector's Edition: - Estátua - Artbook ..." → ["Estátua", "Artbook", ...]
function editionContents(text) {
    const lines = text.split("\n");
    const start = lines.findIndex(l => /conte[uú]do|inclui|includes|cont[eé]m/i.test(l));
    if (start < 0) return [];
    const items = [];
    // items on the same line: "Conteúdo: - A - B - C"
    const sameLine = lines[start].split(/\s[-–•]\s/).slice(1);
    if (sameLine.length > 1) return sameLine.map(s => s.trim()).filter(Boolean);
    for (const line of lines.slice(start + 1)) {
        const m = line.match(/^\s*[-–•*·]\s*(.+)/);
        if (!m) { if (items.length) break; else continue; }
        items.push(m[1].trim());
    }
    return items;
}

// What a special edition includes, from the store descriptions, with the stores' photos
function editionInfo(edition) {
    if (edition.name === "Standard" || (!edition.descriptions.length && !edition.photos.length)) return "";
    let text = "";
    if (edition.descriptions.length) {
        const withList = edition.descriptions.map(d => ({ ...d, items: editionContents(d.text) })).find(d => d.items.length);
        const source = withList || edition.descriptions[0];
        const body = withList
            ? `<ul class="mb-1">${withList.items.map(i => `<li>${esc(i)}</li>`).join("")}</ul>`
            : clampedText(source.text, 4);
        text = `${body}<div class="small text-body-secondary">${esc(t("according_to", { store: storeName(source.store) }))}</div>`;
    }
    return `
        <div class="edition-info mb-3">
            <h3 class="h6 mb-1">${t("whats_included")}</h3>
            ${text}
            ${editionPhotos(edition.photos)}
        </div>`;
}

function editionPhotos(photos) {
    if (!photos.length) return "";
    const stores = [...new Set(photos.map(p => storeName(p.store)))].join(", ");
    return `
        <div class="screenshots mt-2">${photos.map(p => `
            <a href="${esc(p.url)}" target="_blank" rel="noopener">
                <img src="${esc(p.url)}" alt="${t("photo")}" loading="lazy"></a>`).join("")}</div>
        <div class="small text-body-secondary">${esc(t("photos_from", { store: stores }))}</div>`;
}

function renderEdition(edition, i) {
    const card = document.createElement("section");
    card.className = "card shadow-sm mb-4";

    const low = edition.lowest_price;
    const best = edition.offers.find(o => o.in_stock);
    // A store dropped it to the lowest price ever: the same rule as the cards' badge and the tag
    // (app/services/tag_service.py, AT_HISTORICAL_LOW)
    const isLowNow = edition.at_historical_low;

    card.innerHTML = `
        <div class="card-body">
            <h2 class="h5 mb-3">${esc(localName(edition))}
                ${edition.digital_code ? `<span class="badge text-bg-warning ms-1 align-middle"
                    title="${t("digital_code_hint")}">${t("digital_code")}</span>` : ""}</h2>

            ${editionInfo(edition)}

            <div class="d-flex flex-wrap gap-2 mb-3">
                ${best && game.editions.length > 1 ? `<span class="badge bg-body-secondary text-body border fs-6 fw-normal text-wrap text-start">
                    ${t("best_price_now")} <strong>${eur.format(best.price)}</strong> · ${esc(storeName(best.store))}</span>` : ""}
                ${low ? `<span class="badge low-badge fs-6 fw-normal text-wrap text-start">
                    ${t("historical_low")} <strong>${eur.format(low.price)}</strong> · ${fmtDate(low.date)} · ${esc(storeName(low.store))}</span>` : ""}
                ${isLowNow ? `<span class="badge text-bg-success fs-6 fw-normal">${t("lowest_ever_now")}</span>` : ""}
            </div>
            <div class="d-flex flex-wrap gap-2 mb-3" data-collection="${edition.id}"></div>

            ${offersTable(edition)}

            <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-4 mb-2">
                <h3 class="h6 mb-0">${t("price_history")} <span class="text-body-secondary fw-normal small">${t("new_copies")}</span></h3>
                ${periodButtons()}
            </div>
            <div class="chart-box"><canvas id="chart-${i}" role="img"
                aria-label="${esc(t("price_history_of", { name: localName(edition) }))}"></canvas></div>
            <p class="small text-body-secondary mt-1 mb-0">${t("dashed_sold_out")}</p>

            <details class="mt-2">
                <summary class="small">${t("history_table")}</summary>
                ${historyTable(edition)}
            </details>
        </div>`;
    return card;
}

// The chart period (30 days … all time): the same for every chart on the page
function periodButtons() {
    const periods = [[30, "days_30"], [90, "days_90"], [365, "year_1"], [0, "all_time"]];
    return `<div class="btn-group btn-group-sm" role="group" aria-label="${esc(t("period"))}">${periods.map(([days, key]) => `
        <button type="button" class="btn ${days === rangeDays ? "btn-primary active" : "btn-secondary"}" data-days="${days}"
            aria-pressed="${days === rangeDays}">${t(key)}</button>`).join("")}</div>`;
}

function offersTable(edition) {
    const rows = edition.offers.map(o => `
        <tr class="${o.in_stock ? "" : "text-body-secondary"}">
            <td><span class="swatch" style="background:${storeColor(o.store)}"></span>${esc(storeName(o.store))}
                ${o.condition === "used" ? `<span class="badge text-bg-secondary d-sm-none ms-1">${t("used")}</span>` : ""}</td>
            <td class="d-none d-sm-table-cell">${o.condition === "used" ? `<span class="badge text-bg-secondary">${t("used")}</span>` : t("new")}</td>
            <td class="text-end">
                ${o.was_price ? `<small class="text-decoration-line-through text-body-secondary me-1">${eur.format(o.was_price)}</small>
                    <span class="badge text-bg-danger me-1">-${o.discount_percent}%</span>` : ""}
                <strong>${eur.format(o.price)}</strong>
            </td>
            <td>${o.is_preorder ? `<span class="badge text-bg-primary">${t("preorder")}</span>` : o.in_stock ? t("in_stock") : t("sold_out")}</td>
            <td class="text-end"><a href="${esc(o.url)}" target="_blank" rel="noopener"
                class="btn btn-sm offer-link ${o.in_stock ? "btn-primary" : "btn-secondary"}"
                aria-label="${esc(t("view_at", { store: storeName(o.store) }))}"><span class="d-none d-sm-inline">${t("view_in_store")}</span><span
                class="d-sm-none" aria-hidden="true">${t("store_short")} ↗</span></a></td>
        </tr>`).join("");

    return `
        <div class="table-responsive">
            <table class="table table-sm align-middle mb-0 prices">
                <thead><tr><th>${t("col_store")}</th><th class="d-none d-sm-table-cell">${t("col_condition")}</th><th class="text-end">${t("col_price")}</th><th>${t("col_stock")}</th><th></th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
}

function editionHistory(edition) {
    return history.filter(o => o.edition_id === edition.id && o.condition === "new");
}

function historyTable(edition) {
    const low = edition.lowest_price;
    const rows = editionHistory(edition)
        .flatMap(o => o.history.map(p => ({ ...p, store: o.store, offer_id: o.offer_id })))
        .sort((a, b) => b.date.localeCompare(a.date))
        .map(p => {
            const isLow = low && p.offer_id === low.offer_id && p.date === low.date;
            return `<tr class="${isLow ? "table-success" : ""}">
                <td>${fmtDateTime(p.date)}</td><td>${esc(storeName(p.store))}</td>
                <td class="text-end">${eur.format(p.price)}${isLow ? " ★" : ""}</td>
                <td>${p.in_stock ? t("in_stock") : t("sold_out")}</td></tr>`;
        }).join("");

    return `<table class="table table-sm mt-2 mb-0 prices">
        <thead><tr><th>${t("col_date")}</th><th>${t("col_store")}</th><th class="text-end">${t("col_price")}</th><th>${t("col_stock")}</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="4" class="text-body-secondary">${t("no_history")}</td></tr>`}</tbody></table>`;
}

// The copies people sell for this game (render() runs again on theme changes: loaded once)
let marketLoaded = false;
async function loadMarket() {
    document.getElementById("sell-link").href = `/sell?game_id=${GAME_ID}`;
    if (marketLoaded) return;
    marketLoaded = true;
    const listings = await fetch(`/api/listings?game_id=${GAME_ID}`).then(r => r.json()).catch(() => []);
    document.getElementById("market-listings").innerHTML = listings.map(l => listingCard(l)).join("");
    document.getElementById("market-empty").classList.toggle("d-none", listings.length > 0);
}

// Vertical crosshair under the cursor
const crosshair = {
    id: "crosshair",
    afterDatasetsDraw(chart) {
        const active = chart.tooltip?.getActiveElements?.() || [];
        if (!active.length) return;
        const x = active[0].element.x, { top, bottom } = chart.chartArea, ctx = chart.ctx;
        ctx.save();
        ctx.strokeStyle = css("--baseline");
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
        ctx.restore();
    },
};

function drawCharts() {
    charts.forEach(c => c.destroy());
    charts.length = 0;

    const now = new Date();
    const rangeStart = rangeDays ? new Date(now - rangeDays * 86400000) : null;

    game.editions.forEach((edition, i) => {
        const low = edition.lowest_price;
        const activeOffers = new Set(edition.offers.map(o => o.offer_id));
        const offers = editionHistory(edition);
        const allDates = offers.flatMap(o => o.history.map(p => new Date(p.date)));
        if (!allDates.length) return;

        const firstDate = new Date(Math.min(...allDates));
        const xMin = rangeStart && rangeStart > firstDate ? rangeStart : firstDate;

        const datasets = offers.map(o => {
            const color = storeColor(o.store);
            const points = o.history.map(p => ({ x: new Date(p.date), y: p.price, in_stock: p.in_stock, date: p.date }));
            // The last price still holds today for products the store still sells
            const last = points[points.length - 1];
            if (activeOffers.has(o.offer_id)) points.push({ ...last, x: now, extended: true });

            const isLow = p => low && o.offer_id === low.offer_id && p.date === low.date && !p.extended;
            return {
                label: storeName(o.store),
                data: points,
                stepped: true,
                borderColor: color,
                backgroundColor: color,
                borderWidth: 2,
                borderCapStyle: "round",
                borderJoinStyle: "round",
                segment: { borderDash: ctx => ctx.p0.raw.in_stock ? undefined : [4, 4] },
                pointRadius: ctx => isLow(ctx.raw) ? 6 : 0,
                pointHoverRadius: 5,
                pointBorderColor: css("--surface-1"),
                pointBorderWidth: ctx => isLow(ctx.raw) ? 2 : 1,
                pointHitRadius: 8,
            };
        });

        const annotations = low ? {
            lowLine: {
                type: "line",
                yMin: low.price, yMax: low.price,
                borderColor: css("--text-secondary"),
                borderWidth: 1,
                label: {
                    display: true,
                    content: t("chart_low", { price: eur.format(low.price) }),
                    position: "start",
                    color: css("--text-primary"),
                    backgroundColor: css("--surface-1"),
                    font: { size: 11, weight: "600" },
                    padding: 3,
                    yAdjust: -10,
                },
            },
        } : {};

        Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';
        charts.push(new Chart(document.getElementById(`chart-${i}`), {
            type: "line",
            data: { datasets },
            plugins: [crosshair],
            options: {
                maintainAspectRatio: false,
                animation: false,
                interaction: { mode: "nearest", axis: "x", intersect: false },
                scales: {
                    x: {
                        type: "time",
                        min: xMin, max: now,
                        time: { tooltipFormat: "dd/MM/yyyy HH:mm", displayFormats: { hour: "HH:mm", day: "dd/MM", week: "dd/MM", month: "MM/yyyy" } },
                        grid: { color: css("--gridline") },
                        border: { color: css("--baseline") },
                        ticks: { color: css("--text-muted"), maxTicksLimit: 8 },
                    },
                    y: {
                        grace: "10%",
                        grid: { color: css("--gridline") },
                        border: { display: false },
                        ticks: { color: css("--text-muted"), callback: v => eur.format(v) },
                    },
                },
                plugins: {
                    legend: {
                        display: datasets.length > 1,
                        align: "start",
                        labels: { color: css("--text-secondary"), boxWidth: 16, boxHeight: 3 },
                    },
                    tooltip: {
                        callbacks: {
                            label: ctx => {
                                const p = ctx.raw;
                                return `${ctx.dataset.label}: ${eur.format(p.y)}${p.in_stock ? "" : ` ${t("chart_sold_out")}`}${p.extended ? ` ${t("chart_current")}` : ""}`;
                            },
                        },
                    },
                    annotation: { annotations },
                },
            },
        }));
    });
}

// Period buttons (one group per chart, one setting): the selected one solid blue, the others grey
document.addEventListener("click", e => {
    const btn = e.target.closest("[data-days]");
    if (!btn) return;
    rangeDays = Number(btn.dataset.days);
    document.querySelectorAll("[data-days]").forEach(b => {
        const selected = Number(b.dataset.days) === rangeDays;
        b.classList.toggle("active", selected);
        b.classList.toggle("btn-primary", selected);
        b.classList.toggle("btn-secondary", !selected);
        b.setAttribute("aria-pressed", selected);
    });
    drawCharts();
});

// toggleDark(): static/common.js. The charts read their colours from CSS, so redraw them
function onThemeChange() {
    if (game) render();
}

// Back to the search or front page tab this game was opened from (remembered by the
// search page for this browser tab); works after reloads and doesn't rely on browser history
function setBackLink() {
    const last = saved("lastListPage", null, "sessionStorage");
    if (!last || !last.startsWith("/?")) return;   // only our own pages
    const link = document.getElementById("back-link");
    link.href = last;
    if (new URLSearchParams(last.slice(1)).get("q")) link.textContent = t("back_search");
}

// --- the user's collection: "Tenho" / "Quero" per edition (app/services/collection_service.py) ---
const accountReady = renderAccountArea();
let collectionIds = null;      // {edition_id: {owned?: item id, wishlist?: item id}}, loaded once

async function fillCollectionButtons() {
    await accountReady;
    if (currentUser && collectionIds === null) {
        collectionIds = await fetch("/api/collection/editions").then(r => r.ok ? r.json() : {}).catch(() => ({}));
    }
    document.querySelectorAll("[data-collection]").forEach(box => {
        const mine = (collectionIds || {})[box.dataset.collection] || {};
        box.innerHTML = ["owned", "wishlist"].map(kind => `
            <button type="button" class="btn btn-sm ${mine[kind] ? "btn-primary" : "btn-secondary"}" data-kind="${kind}"
                    aria-pressed="${!!mine[kind]}">${t(mine[kind] ? `collection_in_${kind}` : `collection_add_${kind}`)}</button>`).join("")
            + (mine.owned || mine.wishlist ? `<a href="/collection${mine.owned ? "" : "?tab=wishlist"}" class="btn btn-sm btn-link">${t("collection_open")}</a>` : "");
        box.querySelectorAll("[data-kind]").forEach(b => b.onclick = () => toggleCollection(Number(box.dataset.collection), b.dataset.kind));
    });
}

async function toggleCollection(editionId, kind) {
    if (!currentUser) return location.assign(`/account?next=${encodeURIComponent(location.pathname)}`);
    const mine = collectionIds[editionId] || {};
    const { ok, data } = mine[kind]
        ? await api(`/api/collection/${mine[kind]}`, { method: "DELETE" })
        : await api("/api/collection", { body: { edition_id: editionId, kind } });
    if (!ok) return;
    collectionIds = await fetch("/api/collection/editions").then(r => r.json());   // "owned" also clears the wish
    fillCollectionButtons();
}

// --- players' reviews (app/services/review_service.py) ---
let reviewPage = null;          // the API's answer: {summary, mine, reviews, page, pages}
let reviewsLoaded = false, editingReview = false;

// render() runs again on theme changes: load once, and don't redraw a form being written
async function loadReviewsOnce() {
    if (reviewsLoaded) return;
    reviewsLoaded = true;
    document.getElementById("reviews-more").onclick = () => loadReviews(reviewPage.page + 1);
    await accountReady;
    loadReviews(1);
}

async function loadReviews(page) {
    const data = await fetch(`/api/games/${GAME_ID}/reviews?page=${page}`).then(r => r.ok ? r.json() : null).catch(() => null);
    if (!data) return;
    if (page > 1) data.reviews = reviewPage.reviews.concat(data.reviews);
    showReviews(data);
}

function showReviews(data) {
    reviewPage = data;
    const { summary, reviews, page, pages } = data;
    document.getElementById("reviews-platform").textContent = t("reviews_platform", { platform: game.platform_name });
    const most = Math.max(1, ...summary.distribution);
    const bar = (score, n) => `
        <div class="d-flex align-items-center gap-2">
            <span class="small text-end" style="width: 1.25rem;">${score}</span>
            <div class="progress flex-fill" style="height: .5rem;" role="progressbar" aria-valuemin="0"
                 aria-valuemax="${summary.count}" aria-valuenow="${n}" aria-label="${esc(t("reviews_bar", { score, count: n }))}">
                <div class="progress-bar" style="width: ${100 * n / most}%"></div></div>
            <span class="small text-body-secondary" style="width: 1.5rem;">${n}</span>
        </div>`;
    document.getElementById("reviews-summary").innerHTML = summary.count ? `
        <div class="text-center">
            <div class="display-6 fw-semibold">${fmtNumber(summary.average)}<span class="fs-6 text-body-secondary">/10</span></div>
            <div class="small text-body-secondary">${esc(summary.count === 1 ? t("reviews_count_one") : t("reviews_count", { count: summary.count }))}</div>
        </div>
        <div class="review-bars flex-fill">${summary.distribution.map((n, i) => bar(i + 1, n)).reverse().join("")}</div>`
        : `<p class="small text-body-secondary mb-0">${esc(t("reviews_none"))}</p>`;
    renderMyReview();
    const list = document.getElementById("reviews-list");
    list.innerHTML = reviews.filter(r => !r.mine).map(reviewItem).join("");
    bindClampToggles(list);
    document.getElementById("reviews-more").classList.toggle("d-none", page >= pages);
}

function scoreBadge(score) {
    const style = score >= 8 ? "text-bg-success" : score >= 5 ? "text-bg-warning" : "text-bg-danger";
    return `<span class="badge ${style} fs-6">${score}/10</span>`;
}

function reviewItem(r) {
    return `<article class="border-top pt-3">
        <div class="d-flex flex-wrap align-items-center gap-2 mb-1">${scoreBadge(r.score)}
            ${r.title ? `<strong>${esc(r.title)}</strong>` : ""}</div>
        ${r.body ? clampedText(r.body, 5) : ""}
        <div class="small text-body-secondary mt-1">
            ${userLink(r.username)}
            ${r.owner ? `<span class="badge bg-body-secondary text-body border" title="${esc(t("review_owner_hint"))}">📚 ${esc(t("review_owner"))}</span>` : ""}
            · ${fmtDate(r.created_at)}${r.edited ? ` (${esc(t("review_edited"))})` : ""}
            ${r.mine ? "" : `· ${reportButton("review", r.id)}`}
        </div>
    </article>`;
}

// The user's own review (with Edit / Delete), the form, or a link to log in
function renderMyReview() {
    const box = document.getElementById("review-mine");
    const mine = reviewPage.mine;
    if (!currentUser) {
        box.innerHTML = `<a href="/account?next=${encodeURIComponent(location.pathname)}" class="small">${esc(t("reviews_login"))}</a>`;
    } else if (editingReview) {
        box.innerHTML = reviewForm(mine);
        const form = box.querySelector("form");
        form.querySelector("[value=cancel]").onclick = () => { editingReview = false; renderMyReview(); };
        form.onsubmit = e => { e.preventDefault(); saveReview(form); };
    } else if (mine) {
        box.innerHTML = `<h3 class="h6">${esc(t("review_yours"))}</h3>
            ${mine.hidden ? `<div class="alert alert-warning py-1 px-2 small mb-2">${esc(t("review_hidden"))}</div>` : ""}
            ${reviewItem({ ...mine, mine: true })}
            ${mine.hidden ? "" : `<div class="d-flex gap-2 mt-2">
                <button type="button" class="btn btn-sm btn-primary" data-review="edit">${esc(t("review_edit"))}</button>
                <button type="button" class="btn btn-sm btn-danger" data-review="delete">${esc(t("review_delete"))}</button>
            </div>`}`;
        bindClampToggles(box);
        box.querySelector("[data-review=edit]")?.addEventListener("click", () => { editingReview = true; renderMyReview(); });
        box.querySelector("[data-review=delete]")?.addEventListener("click", deleteReview);
    } else {
        box.innerHTML = `<button type="button" class="btn btn-sm btn-primary">${esc(t("review_write"))}</button>`;
        box.querySelector("button").onclick = () => { editingReview = true; renderMyReview(); };
    }
}

function reviewForm(mine) {
    const scores = Array.from({ length: 10 }, (_, i) => i + 1).map(n => `
        <input type="radio" class="btn-check" name="score" id="score-${n}" value="${n}" required ${mine?.score === n ? "checked" : ""}>
        <label class="btn btn-sm btn-secondary" for="score-${n}">${n}</label>`).join("");
    return `<form class="border rounded p-2 p-sm-3">
        <fieldset class="mb-2">
            <legend class="form-label small mb-1">${esc(t("review_score"))}</legend>
            <div class="review-scores">${scores}</div>
        </fieldset>
        <label for="review-title" class="form-label small">${esc(t("review_title_label"))}</label>
        <input id="review-title" name="title" maxlength="120" class="form-control form-control-sm mb-2" value="${esc(mine?.title || "")}">
        <label for="review-body" class="form-label small">${esc(t("review_body_label"))}</label>
        <textarea id="review-body" name="body" maxlength="4000" rows="4" class="form-control form-control-sm mb-2">${esc(mine?.body || "")}</textarea>
        <div class="alert d-none py-1 px-2 small" role="alert"></div>
        <div class="d-flex justify-content-end gap-2">
            <button type="button" value="cancel" class="btn btn-sm btn-secondary">${esc(t("cancel"))}</button>
            <button type="submit" class="btn btn-sm btn-primary">${esc(t("review_save"))}</button>
        </div>
    </form>`;
}

async function saveReview(form) {
    const fields = form.elements;     // form.title would be the form's own title attribute
    const { ok, data } = await api(`/api/games/${GAME_ID}/reviews/mine`, { method: "PUT",
        body: { score: Number(fields.score.value), title: fields.title.value, body: fields.body.value } });
    if (!ok) {
        const message = form.querySelector(".alert");
        message.className = "alert alert-warning py-1 px-2 small";
        message.textContent = t(`error_${data?.error || "unknown"}`);
        return;
    }
    editingReview = false;
    showReviews(data);
}

async function deleteReview() {
    if (!confirm(t("review_delete_confirm"))) return;
    const { ok, data } = await api(`/api/games/${GAME_ID}/reviews/mine`, { method: "DELETE" });
    if (ok) showReviews(data);
}

applyI18n();
setBackLink();   // after applyI18n, which sets the default "← Voltar"
load();
