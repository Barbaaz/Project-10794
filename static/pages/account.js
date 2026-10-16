// The account page (templates/account.html). A file, not inline: the site's CSP only runs scripts from files.
// After logging in: back to where the visitor came from (only our own pages, never another site)
function nextPage() {
    const next = new URLSearchParams(location.search).get("next") || "/";
    return next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

const RESET_TOKEN = new URLSearchParams(location.search).get("reset");    // from the emailed link

function showForm(name) {
    document.querySelectorAll("[data-form]").forEach(b => {
        const selected = b.dataset.form === name;
        b.classList.toggle("active", selected);
        b.setAttribute("aria-selected", selected);
    });
    ["login", "register", "forgot", "reset"].forEach(f =>
        document.getElementById(`${f}-form`).classList.toggle("d-none", name !== f));
}

document.querySelectorAll("[data-form]").forEach(b => b.onclick = () => showForm(b.dataset.form));
document.querySelectorAll("[data-show]").forEach(b => b.onclick = () => showForm(b.dataset.show));

// done(): what happens after it worked (by default, back to where the visitor came from)
function handleForm(id, path, { extra = {}, method = "POST", done = () => location.assign(nextPage()) } = {}) {
    const form = document.getElementById(id);
    const message = form.querySelector(".alert");
    form.onsubmit = async event => {
        event.preventDefault();
        message.className = "alert alert-danger d-none py-2";
        const button = form.querySelector("button[type=submit]");
        button.disabled = true;
        const { ok, data } = await api(path, { method, body: { ...Object.fromEntries(new FormData(form)), ...extra } });
        button.disabled = false;
        if (ok) return done(message, data);
        message.textContent = t(`error_${data?.error || "unknown"}`);
        message.classList.remove("d-none");
    };
}

handleForm("login-form", "/api/auth/login", { extra: { lang: LANG } });
handleForm("register-form", "/api/auth/register", { extra: { lang: LANG } });
handleForm("forgot-form", "/api/auth/forgot", { extra: { lang: LANG }, done: message => {
    message.className = "alert alert-success py-2";
    message.textContent = t("forgot_sent");
} });
handleForm("reset-form", "/api/auth/reset", { extra: { token: RESET_TOKEN }, done: () => location.assign("/account") });
handleForm("password-form", "/api/auth/password", { done: message => {
    document.getElementById("password-form").reset();
    message.className = "alert alert-success py-2";
    message.textContent = t("password_changed");
} });
handleForm("profile-form", "/api/auth/profile", { method: "PATCH", done: (message, user) => {
    message.className = "alert alert-success py-2";
    message.textContent = t("profile_saved");
    showAccount(user);
    fillAccounts(user);
} });

// The gamer names and channels as they're kept (gaming_accounts), back in the boxes the way they can be typed
function fillAccounts(user) {
    const form = document.getElementById("profile-form");
    const typed = (kind, value) =>
        kind === "steam" ? (value.startsWith("id/") ? value.slice(3) : `https://steamcommunity.com/${value}`)
        : kind === "youtube" && value.startsWith("channel/") ? `https://www.youtube.com/${value}` : value;
    form.querySelectorAll("fieldset input").forEach(input => input.value = typed(input.name, user.accounts?.[input.name] || ""));
}
handleForm("delete-form", "/api/auth/delete", { done: () => location.assign("/") });
// the button (and Enter in the password box) only works once the box is ticked
const deleteConfirm = document.getElementById("delete-confirm");
deleteConfirm.onchange = () =>
    document.querySelector("#delete-form button[type=submit]").disabled = !deleteConfirm.checked;

// The profile picture: uploaded as soon as it's chosen; the server makes it a square without metadata
function showAvatar(user) {
    document.getElementById("avatar-preview").innerHTML = avatarImage(user.avatar, 72);
    document.getElementById("avatar-remove").classList.toggle("d-none", !user.avatar);
}
function avatarDone(ok, data) {
    const message = document.getElementById("avatar-message");
    message.className = `small mb-2 ${ok ? "text-success" : "text-danger"}`;
    message.textContent = ok ? t("avatar_saved") : t(`error_${data?.error || "unknown"}`);
    if (ok) { showAvatar(data); currentUser = data; renderAccountArea(); }
}
document.getElementById("avatar-file").onchange = async event => {
    const file = event.target.files[0];
    if (!file) return;
    const form = new FormData();
    form.append("avatar", file);
    const response = await fetch("/api/auth/avatar", { method: "POST", body: form, headers: { "X-Requested-With": "fetch" } });
    avatarDone(response.ok, await response.json().catch(() => null));
    event.target.value = "";
};
document.getElementById("avatar-remove").onclick = async () => {
    const { ok, data } = await api("/api/auth/avatar", { method: "DELETE" });
    avatarDone(ok, data);
};

function showAccount(user) {
    showAvatar(user);
    const facts = [
        [t("username"), user.username],
        [t("display_name"), user.display_name],
        [t("profile_location"), user.location || "—"],
        [t("email"), user.email],
        [t("member_since"), new Date(user.created_at).toLocaleDateString(LOCALE)],
    ];
    document.getElementById("account-facts").innerHTML = facts.map(([k, v]) =>
        `<dt class="col-sm-4 text-body-secondary">${esc(k)}</dt><dd class="col-sm-8">${esc(v)}</dd>`).join("");
}

async function load() {
    const user = await fetch("/api/auth/me").then(r => r.json()).catch(() => null);
    document.getElementById("loading").classList.add("d-none");
    if (!user || RESET_TOKEN) {
        document.getElementById("logged-out").classList.remove("d-none");
        if (RESET_TOKEN) showForm("reset");
        else if (location.hash === "#register") showForm("register");
        return;
    }
    showAccount(user);
    const form = document.getElementById("profile-form");
    form.display_name.value = user.display_name || "";
    form.location.value = user.location || "";
    fillAccounts(user);
    document.getElementById("profile-view").href = `/user/${encodeURIComponent(user.username)}`;
    if (location.hash) document.querySelector(location.hash)?.scrollIntoView();
    loadSettings(user);
    document.getElementById("logout").onclick = async () => {
        await api("/api/auth/logout");
        location.assign("/");
    };
    document.getElementById("logged-in").classList.remove("d-none");

    const mine = await fetch("/api/listings/mine").then(r => r.json()).catch(() => []);
    document.getElementById("my-listings-grid").innerHTML = mine.map(l => listingCard(l, { showSeller: false })).join("");
    document.getElementById("my-listings-empty").classList.toggle("d-none", mine.length > 0);
}

// The collection's privacy, the e-mails and the Steam / PSN accounts (collection_service.settings,
// steam_service / psn_service.saved_profile); each switch saved as it changes
// Push notifications on this device: the switch asks the browser, then the server keeps where to send
// (common.js pushOn / pushOff); "Enviar um teste" shows one at once
async function setUpPush() {
    const box = document.getElementById("push-on"), state = document.getElementById("push-state");
    const test = document.getElementById("push-test");
    const show = (on, note = "", error = false) => {
        box.checked = on;
        test.classList.toggle("d-none", !on);
        state.className = `small mt-1 ${error ? "text-danger" : "text-body-secondary"}`;
        state.textContent = note;
    };
    const support = pushSupport();
    if (support === "unsupported") {
        box.disabled = true;
        const apple = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
        return show(false, t(apple ? "push_ios" : "push_unsupported"));
    }
    if (support === "denied") {
        box.disabled = true;
        return show(false, t("push_blocked"));
    }
    const subscription = await pushSubscription().catch(() => null);
    // on already: the server is told again (it may have been another user's on this device, or forgotten)
    show(!!subscription && support === "granted" && await pushOn().catch(() => false));
    box.onchange = async () => {
        box.disabled = true;
        try {
            if (box.checked) {
                const on = await pushOn();
                show(on, on ? t("push_on") : t(pushSupport() === "denied" ? "push_blocked" : "push_not_allowed"), !on);
                if (pushSupport() === "denied") return;
            } else {
                await pushOff();
                show(false, t("push_off"));
            }
        } catch (e) {
            show(false, t("push_failed"), true);
        }
        box.disabled = false;
    };
    test.onclick = async () => {
        const { ok, data } = await api("/api/push/test");
        show(true, ok && data.sent ? t("push_test_sent") : t("push_failed"), !(ok && data.sent));
    };
}

async function loadSettings(user) {
    const settings = await fetch("/api/collection/settings").then(r => r.ok ? r.json() : null).catch(() => null);
    if (!settings) return;
    const page = document.getElementById("settings-collection-page");
    page.href = `/user/${encodeURIComponent(user.username)}/collection`;
    document.getElementById("settings-showcase").href = `/user/${encodeURIComponent(user.username)}`;
    const showPublic = open => {
        document.getElementById("settings-public").checked = open;
        document.getElementById("settings-public-text").textContent = t(open ? "collection_public_on_text" : "collection_public_off_text");
        page.classList.toggle("d-none", !open);
    };
    showPublic(settings.public);
    document.getElementById("settings-alerts").checked = settings.wish_alerts;
    document.getElementById("settings-lang").value = settings.lang;
    // "Guardado" under the section that changed (the collection switch is under Privacidade)
    const save = async (changes, undo, message = document.getElementById("settings-message")) => {
        const { ok, data } = await api("/api/collection/settings", { method: "PUT", body: changes });
        message.className = `small mt-2 ${ok ? "text-success" : "text-danger"}`;
        message.textContent = ok ? t("collection_saved") : t(`error_${data?.error || "unknown"}`);
        if (!ok) undo();
        return ok;
    };
    document.getElementById("settings-public").onchange = async e => {
        if (await save({ public: e.target.checked }, () => e.target.checked = !e.target.checked,
                       document.getElementById("privacy-message"))) showPublic(e.target.checked);
    };
    document.getElementById("settings-alerts").onchange = e => save({ wish_alerts: e.target.checked }, () => e.target.checked = !e.target.checked);
    document.getElementById("settings-lang").onchange = e => save({ lang: e.target.value }, () => e.target.value = settings.lang);

    // the header's bell: on / off, which deals count, the smallest discount; each saved as it changes
    const bell = settings.notify;
    const showBell = () => {
        document.getElementById("bell-on").checked = bell.bell;
        document.querySelectorAll("[data-bell]").forEach(box => box.checked = bell[box.dataset.bell]);
        document.getElementById("bell-min").value = String(bell.min_discount);
        document.querySelectorAll("#bell-kinds input, #bell-kinds select").forEach(el => el.disabled = !bell.bell);
    };
    const saveBell = async (key, value) => {
        const before = bell[key];
        bell[key] = value;
        showBell();
        await save({ notify: { [key]: value } }, () => { bell[key] = before; showBell(); });
        showNotifications();          // the header's bell counts again
    };
    document.getElementById("bell-on").onchange = e => saveBell("bell", e.target.checked);
    document.querySelectorAll("[data-bell]").forEach(box => box.onchange = () => saveBell(box.dataset.bell, box.checked));
    document.getElementById("bell-min").onchange = e => saveBell("min_discount", Number(e.target.value));
    showBell();
    setUpPush();

    const [steam, psn] = await Promise.all(["steam", "psn"].map(key =>
        fetch(`/api/collection/${key}`).then(r => r.ok ? r.json() : {}).catch(() => ({}))));
    const when = at => at ? new Date(at).toLocaleString(LOCALE, { dateStyle: "short", timeStyle: "short" }) : "";
    const row = (symbol, name, profile, who) => `
        <div class="connection">
            <span aria-hidden="true" class="text-primary">${symbol}</span>
            <div class="flex-grow-1 min-w-0"><div class="fw-semibold small">${esc(name)}</div>
                <div class="small text-body-secondary text-truncate">${profile
                    ? esc(`${who} · ${t("steam_last_import", { date: when(profile.imported_at) })}`)
                    : esc(t("settings_not_connected"))}</div></div>
            <a href="/collection" class="btn btn-sm btn-secondary">${esc(t(profile ? "settings_refresh" : "settings_import"))}</a>
        </div>`;
    document.getElementById("settings-connections").innerHTML =
        row(icon("gamepad", 20), "Steam", steam.profile, steam.profile?.steam_id) + row(icon("gamepad", 20), "PlayStation Network", psn.profile, psn.profile?.online_id);
}

// The section in view is the one marked in the menu
const sections = [...document.querySelectorAll(".settings-section")];
const menuLinks = [...document.querySelectorAll(".settings-nav a")];
if ("IntersectionObserver" in window) {
    const seen = new IntersectionObserver(entries => entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        menuLinks.forEach(a => {
            const on = a.getAttribute("href") === `#${entry.target.id}`;
            a.classList.toggle("active", on);
            on ? a.setAttribute("aria-current", "true") : a.removeAttribute("aria-current");
        });
    }), { rootMargin: "-20% 0px -70% 0px" });
    sections.forEach(section => seen.observe(section));
}

applyI18n();
renderAccountArea();
load();
