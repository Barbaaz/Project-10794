// The most anticipated games, one at a time: Lançamentos (static/pages/index.js) and the home page
// (static/pages/home.js). t(), eur: static/i18n.js; icon(), storeName(), platformsOf(): static/common.js
const SLIDE_MS = 6000;              // each one this long, then the next
let slideTimer = null;
let slideIndex = 0;                 // kept when the calendar redraws the tab
let slidePaused = matchMedia("(prefers-reduced-motion: reduce)").matches;     // no moving by itself then

// The most anticipated of these releases (/api/releases cards), one card per game: the most followed on IGDB,
// then the most wished here; a game's platforms count once
function mostAnticipated(groups, count) {
    const interest = card => Math.max(...(platformsOf(card) || [card]).map(g => g.hypes || 0));
    const wishes = card => (platformsOf(card) || [card]).reduce((n, g) => n + (g.wishes || 0), 0);
    return mergePlatforms(groups).filter(c => interest(c) || wishes(c))
        .sort((a, b) => interest(b) - interest(a) || wishes(b) - wishes(a) || a.release_date.localeCompare(b.release_date))
        .slice(0, count);
}

// The most anticipated, one at a time (user, 2026-10-14: "a slide that changes games automatically and
// highlights each of them"): the next every SLIDE_MS, held while the pointer or the keyboard is on it, a
// pause button (also the default when the device asks for less motion), arrows, dots, a swipe on a phone
function anticipatedSlider(cards) {
    const box = document.createElement("section");
    box.className = "slider mb-4";
    box.setAttribute("aria-roledescription", t("releases_slider"));
    box.setAttribute("aria-label", t("releases_anticipated"));
    slideIndex %= cards.length;
    box.innerHTML = `
        <div class="d-flex align-items-baseline flex-wrap column-gap-2 mb-2">
            <h3 class="h5 mb-0">${esc(t("releases_anticipated"))}</h3>
            <span class="small text-body-secondary">${esc(t("releases_anticipated_hint"))}</span>
        </div>
        <div class="slides">${cards.map((c, i) => slideHtml(c, i, cards.length)).join("")}</div>
        <div class="d-flex align-items-center gap-1 mt-2">
            <button type="button" class="btn btn-sm btn-secondary" data-step="-1" aria-label="${esc(t("releases_slide_prev"))}">&lsaquo;</button>
            <div class="slider-dots">${cards.map((c, i) => `<button type="button" class="dot" data-slide="${i}"
                aria-label="${esc(`${t("releases_slide_of", { n: i + 1, total: cards.length })}: ${localName(c)}`)}"></button>`).join("")}</div>
            <button type="button" class="btn btn-sm btn-secondary" data-step="1" aria-label="${esc(t("releases_slide_next"))}">&rsaquo;</button>
            <button type="button" class="btn btn-sm btn-secondary ms-auto" data-pause></button>
        </div>`;
    const slides = box.querySelectorAll(".slide");
    const dots = box.querySelectorAll("[data-slide]");
    const pause = box.querySelector("[data-pause]");
    let held = false;
    const show = i => {
        slideIndex = (i + cards.length) % cards.length;
        slides.forEach((s, n) => { s.hidden = n !== slideIndex; });
        dots.forEach((d, n) => d.setAttribute("aria-current", n === slideIndex));
    };
    const showPause = () => {
        pause.innerHTML = icon(slidePaused ? "play" : "pause", 14);
        pause.setAttribute("aria-label", t(slidePaused ? "releases_slide_play" : "releases_slide_pause"));
        pause.title = pause.getAttribute("aria-label");
    };
    box.querySelectorAll("[data-step]").forEach(b => b.onclick = () => show(slideIndex + Number(b.dataset.step)));
    dots.forEach(d => d.onclick = () => show(Number(d.dataset.slide)));
    pause.onclick = () => { slidePaused = !slidePaused; showPause(); };
    box.addEventListener("mouseenter", () => { held = true; });
    box.addEventListener("mouseleave", () => { held = false; });
    box.addEventListener("focusin", () => { held = true; });
    box.addEventListener("focusout", e => { if (!box.contains(e.relatedTarget)) held = false; });
    let touchX = null;
    box.addEventListener("touchstart", e => { touchX = e.touches[0].clientX; }, { passive: true });
    box.addEventListener("touchend", e => {
        const dx = e.changedTouches[0].clientX - (touchX ?? e.changedTouches[0].clientX);
        if (Math.abs(dx) > 40) show(slideIndex + (dx < 0 ? 1 : -1));
        touchX = null;
    });
    slideTimer = setInterval(() => {
        if (!box.isConnected) return clearInterval(slideTimer);       // another tab drawn
        if (!slidePaused && !held && !document.hidden) show(slideIndex + 1);
    }, SLIDE_MS);
    show(slideIndex);
    showPause();
    return box;
}

// One slide: the big cover, the platforms, when it's out (and how long to go), how many follow it, the best price
function slideHtml(card, i, total) {
    const all = platformsOf(card) || [card];
    const best = all.flatMap(g => g.offers).filter(o => o.in_stock).sort((a, b) => a.price - b.price)[0];
    const hypes = Math.max(...all.map(g => g.hypes || 0));
    const days = Math.round((parseDay(card.release_date) - parseDay(isoDay(new Date()))) / 86400000);
    const toGo = card.date_is_estimate ? ""
        : days === 0 ? t("releases_out_today") : days === 1 ? t("releases_out_tomorrow") : t("releases_days_left", { count: days });
    const url = `/game/${card.game_id}`;
    return `
        <div class="slide" role="group" aria-roledescription="${esc(t("releases_slide"))}"
             aria-label="${esc(t("releases_slide_of", { n: i + 1, total }))}" ${i === slideIndex ? "" : "hidden"}>
            ${card.cover ? `<img class="slide-bg" src="${esc(card.cover)}" alt="" aria-hidden="true">` : ""}
            <a href="${url}" class="slide-cover" tabindex="-1" aria-hidden="true">${card.cover
                ? `<img src="${esc(card.cover)}" alt="" class="${coverClass(card.cover)}">` : ""}</a>
            <div class="slide-text min-w-0">
                <div class="d-flex flex-wrap gap-1 mb-2">${all.map(g =>
                    `<span class="slide-chip">${esc(PLATFORM_SHORT[g.console] || g.platform_name)}</span>`).join("")}</div>
                <h4 class="slide-title"><a href="${url}">${esc(localName(card))}</a></h4>
                <div class="slide-date">${icon("calendar", 16)} ${esc(releaseLabel(card.release_date, card.date_is_estimate))}${
                    toGo ? ` <span class="badge text-bg-primary ms-1">${esc(toGo)}</span>` : ""}</div>
                ${hypes ? `<div class="small text-body-secondary mt-1">${esc(t("releases_followers", { count: fmtNumber(hypes) }))}</div>` : ""}
                <div class="d-flex flex-wrap align-items-center gap-3 mt-3">
                    ${best ? `<div><span class="slide-price">${eur.format(best.price)}</span>
                        <span class="small text-body-secondary">${esc(storeName(best.store))}</span></div>` : ""}
                    <a class="btn btn-primary btn-sm" href="${url}">${esc(t("releases_slide_go"))}</a>
                </div>
            </div>
        </div>`;
}
