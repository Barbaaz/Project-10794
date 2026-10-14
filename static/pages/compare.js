// The user's collection beside another user's (templates/compare.html; follow_service.compare)
const USERNAME = document.body.dataset.username;
let data = null;
let tab = "both";

// One side's numbers for a game: hours, achievements / trophies, the platinum
function facts(game) {
    if (!game) return "";
    const parts = [
        game.hours ? `${fmtNumber(game.hours)} h` : "",
        game.achievements_total ? `${icon("trophy", 13)} ${game.achievements}/${game.achievements_total}` : "",
        game.platinum ? `<span class="badge text-bg-info">${esc(t("collection_platinum"))}</span>` : "",
        game.finished ? `<span class="badge text-bg-secondary">${esc(t("status_play_finished"))}</span>` : "",
    ].filter(Boolean);
    return parts.join(" ") || "—";
}

function row(game, mine, theirs) {
    const side = (label, g) => `
        <div class="col-6 small"><div class="text-body-secondary">${esc(label)}${g ? ` · ${esc(g.platforms.join(", "))}` : ""}</div>
            <div>${g ? facts(g) : "—"}</div></div>`;
    return `
        <div class="card"><div class="card-body p-2 d-flex gap-2">
            ${game.image ? `<img src="${esc(game.image)}" alt="" class="rounded object-fit-cover flex-shrink-0 ${coverClass(game.image)}" style="width: 56px; aspect-ratio: 3 / 4;">`
                         : `<div class="rounded bg-body-secondary flex-shrink-0" style="width: 56px; aspect-ratio: 3 / 4;"></div>`}
            <div class="flex-grow-1 min-w-0">
                <a href="/game/${game.game_id}" class="fw-semibold small link-body-emphasis text-decoration-none">${esc(localName(game) || "")}</a>
                <div class="row g-1 mt-1">${side(t("compare_you"), mine)}${side(userLabel(data.them.username), theirs)}</div>
            </div>
        </div></div>`;
}

function render() {
    const them = userLabel(data.them.username);
    const lists = { both: data.both, only_them: data.only_them, only_me: data.only_me };
    const box = document.getElementById("tabs");
    box.innerHTML = [["both", t("compare_both", { n: data.both.length })],
                     ["only_them", t("compare_only_them", { user: them, n: data.only_them.length })],
                     ["only_me", t("compare_only_me", { n: data.only_me.length })]].map(([key, label]) =>
        `<button type="button" class="chip-btn" data-tab="${key}" aria-pressed="${tab === key}">${esc(label)}</button>`).join("");
    box.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => { tab = b.dataset.tab; render(); });
    const games = lists[tab];
    document.getElementById("games").innerHTML = games.map(g =>
        tab === "both" ? row(g, g.me, g.them) : tab === "only_me" ? row(g, g, null) : row(g, null, g)).join("");
    document.getElementById("empty").classList.toggle("d-none", games.length > 0);
}

function summary() {
    const pct = s => s.achievements_total ? ` <span class="small text-body-secondary">(${Math.round(100 * s.achievements / s.achievements_total)}%)</span>` : "";
    const lines = [
        ["compare_games", s => fmtNumber(s.games)],
        ["compare_finished", s => fmtNumber(s.finished)],
        ["compare_hours", s => fmtNumber(s.hours)],
        ["compare_achievements", s => s.achievements_total ? `${fmtNumber(s.achievements)} / ${fmtNumber(s.achievements_total)}${pct(s)}` : "—"],
        ["compare_platinums", s => fmtNumber(s.platinums)],
    ];
    document.getElementById("summary").innerHTML = lines.map(([key, value]) => `
        <tr><th scope="row" class="fw-normal">${esc(t(key))}</th>
            <td class="text-end">${value(data.me.summary)}</td><td class="text-end">${value(data.them.summary)}</td></tr>`).join("");
}

async function load() {
    await renderAccountArea();
    if (!currentUser) return location.assign(`/account?next=${encodeURIComponent(location.pathname)}`);
    const response = await fetch(`/api/users/${encodeURIComponent(USERNAME)}/compare`);
    document.getElementById("loading").classList.add("d-none");
    const answer = await response.json().catch(() => ({}));
    if (!response.ok) {
        const error = document.getElementById("error");
        error.textContent = t(answer.error === "not_found" ? "profile_not_found" : `error_${answer.error || "unknown"}`);
        return error.classList.remove("d-none");
    }
    data = answer;
    const them = userLabel(data.them.username);
    document.title = `${t("compare_collections")} · ${them} · SaveOnGames`;
    document.getElementById("title").innerHTML = esc(t("compare_title", { user: "\u0000" })).replace("\u0000",
        `<a href="/user/${encodeURIComponent(data.them.username)}">${esc(them)}</a>`);
    document.getElementById("head-me").textContent = t("compare_you");
    document.getElementById("head-them").textContent = them;
    summary();
    render();
    document.getElementById("compare").classList.remove("d-none");
}
applyI18n();
load();
