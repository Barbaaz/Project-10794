// The messages page (templates/messages.html). A file, not inline: the site's CSP only runs scripts from files.
let conversations = [];
let open = null;          // the conversation on screen
let lastId = 0;           // its newest message shown
const REFRESH_MS = 5000;

const STATUS_STYLES = { requested: "text-bg-warning", accepted: "text-bg-info", sent: "text-bg-primary",
                        completed: "text-bg-success", problem: "text-bg-danger", declined: "text-bg-secondary",
                        cancelled: "text-bg-secondary" };
const STEP_STYLES = { accept: "btn-success", received: "btn-success", sent: "btn-primary", request: "btn-success",
                      decline: "btn-danger", cancel: "btn-danger", problem: "btn-danger" };

function fmtTime(iso) {
    return new Date(iso).toLocaleString(LOCALE, { dateStyle: "short", timeStyle: "short" });
}

async function loadList() {
    conversations = await fetch("/api/conversations").then(r => r.json());
    const list = document.getElementById("chat-list");
    list.innerHTML = conversations.map(c => `
        <a href="?c=${c.id}" data-id="${c.id}" class="list-group-item list-group-item-action d-flex gap-2 align-items-center
            ${open && open.id === c.id ? "active" : ""}">
            <img src="${esc(c.thumb_url || "")}" alt="">
            <div class="flex-fill overflow-hidden">
                <div class="d-flex justify-content-between gap-1">
                    <strong class="text-truncate">${esc(c.title)}</strong>
                    ${c.unread ? `<span class="badge rounded-pill text-bg-danger">${c.unread}</span>` : ""}
                </div>
                <div class="small">@${esc(c.other_username)} · ${t(c.role === "buyer" ? "you_buy" : "you_sell")}</div>
                <div class="small preview opacity-75">${esc(c.last_event ? eventText(c.last_event) : c.last_body || (c.last_photos ? t("chat_photo") : ""))}</div>
            </div>
        </a>`).join("");
    list.querySelectorAll("[data-id]").forEach(a => a.onclick = e => { e.preventDefault(); openChat(Number(a.dataset.id)); });
    document.getElementById("no-chats").classList.toggle("d-none", conversations.length > 0);
    document.getElementById("pick-chat").classList.toggle("d-none", !!open || !conversations.length);
}

async function openChat(id) {
    const response = await fetch(`/api/conversations/${id}`);
    if (!response.ok) return;
    open = await response.json();
    lastId = 0;
    history.replaceState(null, "", `/messages?c=${id}`);
    document.getElementById("chat-messages").innerHTML = "";
    renderChat(open.messages);
    document.getElementById("chat").classList.remove("d-none");
    document.getElementById("pick-chat").classList.add("d-none");
    document.getElementById("chat-layout").classList.add("chat-open");
    loadList();
    showUnreadCount();
}

// Phone: back from a conversation to the list
function closeChat() {
    open = null;
    history.replaceState(null, "", "/messages");
    document.getElementById("chat").classList.add("d-none");
    document.getElementById("chat-layout").classList.remove("chat-open");
    loadList();
    window.scrollTo(0, 0);
}

function eventText(event) {
    return t(`event_${event}`);
}

function renderChat(newMessages) {
    document.getElementById("chat-thumb").src = open.thumb_url || "";
    const listing = document.getElementById("chat-listing");
    listing.href = `/listing/${open.listing_id}`;
    listing.textContent = `${open.title} · ${eur.format(open.price)}`;
    document.getElementById("chat-with").innerHTML =
        `${esc(t(open.role === "buyer" ? "you_buy_from" : "you_sell_to"))} <a href="/user/${encodeURIComponent(open.other_username)}">@${esc(open.other_username)}</a> · ${esc(open.platform_name)}`;
    const status = document.getElementById("chat-status");
    status.className = `badge ${STATUS_STYLES[open.deal_status] || "d-none"}`;
    status.textContent = open.deal_status !== "none" ? t(`deal_${open.deal_status}`) : "";

    const steps = document.getElementById("chat-steps");
    steps.innerHTML = open.steps.map(s => `
        <button type="button" class="btn btn-sm ${STEP_STYLES[s] || "btn-secondary"}" data-step="${s}">${t(`step_${s}_${open.role}`)}</button>`).join("");
    steps.querySelectorAll("[data-step]").forEach(b => b.onclick = () => takeStep(b.dataset.step));
    document.getElementById("step-hint").textContent = t(`hint_${open.deal_status}_${open.role}`, {}, "");
    renderRating();

    const box = document.getElementById("chat-messages");
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    for (const m of newMessages) {
        const row = document.createElement("div");
        if (m.event) {
            row.className = "site-message";
            row.textContent = `${eventText(m.event)} · ${fmtTime(m.created_at)}`;
        } else {
            row.className = `bubble ${m.sender_id === currentUser.id ? "mine" : "theirs"}`;
            const photos = (m.photos || []).map(p => `<a href="${esc(p.url)}" target="_blank" rel="noopener"><img
                src="${esc(p.thumb_url)}" alt="${esc(t("chat_photo_open"))}" loading="lazy"></a>`).join("");
            row.innerHTML = `${photos ? `<div class="photos">${photos}</div>` : ""}${esc(m.body || "")}<span class="time">${fmtTime(m.created_at)}</span>`;
        }
        box.appendChild(row);
        lastId = Math.max(lastId, m.id);
    }
    if (atBottom || newMessages.length) box.scrollTop = box.scrollHeight;
}

// --- ratings (completed purchases) ---------------------------------------------------------
let editingRating = false;

function stars(n) {
    return `<span class="text-warning" aria-label="${esc(t("stars_n", { n }))}">${"★".repeat(n)}${"☆".repeat(5 - n)}</span>`;
}

function renderRating() {
    const box = document.getElementById("chat-rating");
    if (!open.ratings) { box.innerHTML = ""; return; }
    const { mine, theirs } = open.ratings;
    const theirsHtml = theirs
        ? `<div class="small mb-2">${esc(t("their_rating", { user: open.other_username }))} ${stars(theirs.stars)}
             ${theirs.comment ? `<span class="fst-italic">“${esc(theirs.comment)}”</span>` : ""}</div>`
        : `<div class="small text-body-secondary mb-2">${esc(t("their_rating_pending", { user: open.other_username }))}</div>`;

    if (mine && !editingRating) {
        box.innerHTML = `<div class="alert alert-success py-2 mb-2 small">
            ${esc(t("your_rating", { user: open.other_username }))} ${stars(mine.stars)}
            ${mine.comment ? `<span class="fst-italic">“${esc(mine.comment)}”</span>` : ""}
            ${mine.editable ? `<button type="button" id="edit-rating" class="btn btn-sm btn-secondary ms-2">${t("change_rating")}</button>` : ""}
        </div>${theirsHtml}`;
        box.querySelector("#edit-rating")?.addEventListener("click", () => { editingRating = true; renderRating(); });
        return;
    }
    box.innerHTML = `
        <form id="rating-form" class="card card-body py-2 mb-2">
            <div class="fw-semibold small mb-1">${esc(t("rate_user", { user: open.other_username }))}</div>
            <div class="star-input mb-2" role="radiogroup" aria-label="${esc(t("rating_stars"))}">
                ${[5, 4, 3, 2, 1].map(n => `<input type="radio" name="stars" id="star-${n}" value="${n}"
                    ${mine?.stars === n ? "checked" : ""}><label for="star-${n}" title="${esc(t("stars_n", { n }))}">★</label>`).join("")}
            </div>
            <textarea name="comment" rows="2" maxlength="500" class="form-control form-control-sm mb-2"
                      placeholder="${esc(t("rating_comment"))}" aria-label="${esc(t("rating_comment"))}">${esc(mine?.comment || "")}</textarea>
            <button class="btn btn-sm btn-primary align-self-start">${t(mine ? "save_rating" : "send_rating")}</button>
        </form>${theirsHtml}`;
    box.querySelector("#rating-form").onsubmit = async e => {
        e.preventDefault();
        const form = new FormData(e.target);
        if (!form.get("stars")) return chatError("stars_invalid");
        const { ok, data } = await api(`/api/conversations/${open.id}/rating`,
            { body: { stars: Number(form.get("stars")), comment: form.get("comment") } });
        if (!ok) return chatError(data?.error);
        chatError(null);
        open.ratings = data;
        editingRating = false;
        renderRating();
        showPendingRatings();
    };
}

function chatError(code) {
    const box = document.getElementById("chat-error");
    box.textContent = code ? t(`error_${code}`) : "";
    box.classList.toggle("d-none", !code);
}

// After sending / a step, the answer is the whole conversation: show what's new in it
function update(data) {
    const newMessages = data.messages.filter(m => m.id > lastId);
    open = { ...data, messages: undefined };
    renderChat(newMessages);
    loadList();
}

async function takeStep(action) {
    if (["decline", "cancel"].includes(action) && !confirm(t(`confirm_${action}`))) return;
    if (action === "received" && !confirm(t("confirm_received"))) return;
    chatError(null);
    const { ok, data } = await api(`/api/conversations/${open.id}/steps`, { body: { action } });
    if (!ok) return chatError(data?.error);
    update(data);
}

// Photos for the next message: up to MAX_PHOTOS, shown small above the box with a button to take them off
const MAX_PHOTOS = 5;
let chosenPhotos = [];

function renderChosenPhotos() {
    const box = document.getElementById("chosen-photos");
    box.querySelectorAll("img").forEach(img => URL.revokeObjectURL(img.src));
    box.innerHTML = chosenPhotos.map(f => `<img src="${URL.createObjectURL(f)}" alt="">`).join("") + (chosenPhotos.length
        ? `<button type="button" class="btn btn-sm btn-secondary" id="clear-photos">✕ ${esc(t("chat_remove_photos"))}</button>` : "");
    box.classList.toggle("d-none", !chosenPhotos.length);
    box.querySelector("#clear-photos")?.addEventListener("click", () => { chosenPhotos = []; renderChosenPhotos(); });
}

document.getElementById("attach-photos").onclick = () => document.getElementById("chat-photos").click();
document.getElementById("chat-photos").addEventListener("change", e => {
    chosenPhotos = [...chosenPhotos, ...e.target.files];
    e.target.value = "";
    chatError(chosenPhotos.length > MAX_PHOTOS ? "message_photos_many" : null);
    chosenPhotos = chosenPhotos.slice(0, MAX_PHOTOS);
    renderChosenPhotos();
});

document.getElementById("chat-form").onsubmit = async e => {
    e.preventDefault();
    const input = document.getElementById("chat-input");
    if (!input.value.trim() && !chosenPhotos.length) return;
    chatError(null);
    const button = e.target.querySelector("button:not([type])");
    button.disabled = true;
    let ok, data;
    if (chosenPhotos.length) {
        // a form with the files (api() sends JSON); the same header our pages send with every change
        const form = new FormData();
        form.append("body", input.value);
        chosenPhotos.forEach(f => form.append("photos", f));
        const response = await fetch(`/api/conversations/${open.id}/messages`,
            { method: "POST", body: form, headers: { "X-Requested-With": "fetch" } }).catch(() => null);
        ok = response?.ok;
        data = await response?.json().catch(() => null);
    } else {
        ({ ok, data } = await api(`/api/conversations/${open.id}/messages`, { body: { body: input.value } }));
    }
    button.disabled = false;
    if (!ok) return chatError(data?.error || "unknown");
    input.value = "";
    chosenPhotos = [];
    renderChosenPhotos();
    update(data);
};

// Enter sends, Shift+Enter makes a new line
document.getElementById("chat-input").addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); document.getElementById("chat-form").requestSubmit(); }
});

// New messages every few seconds, only while the page is on screen
setInterval(async () => {
    if (!open || document.visibilityState !== "visible") return;
    const response = await fetch(`/api/conversations/${open.id}?after=${lastId}`);
    if (!response.ok) return;
    const data = await response.json();
    const changed = data.messages.length || data.deal_status !== open.deal_status;
    if (changed) update({ ...data, messages: data.messages });
}, REFRESH_MS);

async function start() {
    applyI18n();
    await renderAccountArea();
    if (!currentUser) return location.replace(`/account?next=${encodeURIComponent(location.pathname + location.search)}`);
    const id = Number(new URLSearchParams(location.search).get("c"));
    document.getElementById("back-to-list").onclick = closeChat;
    await loadList();
    if (id) openChat(id);
}
start();
