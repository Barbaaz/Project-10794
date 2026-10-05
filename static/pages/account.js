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
function handleForm(id, path, { extra = {}, done = () => location.assign(nextPage()) } = {}) {
    const form = document.getElementById(id);
    const message = form.querySelector(".alert");
    form.onsubmit = async event => {
        event.preventDefault();
        message.className = "alert alert-danger d-none py-2";
        const button = form.querySelector("button[type=submit]");
        button.disabled = true;
        const { ok, data } = await api(path, { body: { ...Object.fromEntries(new FormData(form)), ...extra } });
        button.disabled = false;
        if (ok) return done(message);
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

async function load() {
    const user = await fetch("/api/auth/me").then(r => r.json()).catch(() => null);
    document.getElementById("loading").classList.add("d-none");
    if (!user || RESET_TOKEN) {
        document.getElementById("logged-out").classList.remove("d-none");
        if (RESET_TOKEN) showForm("reset");
        else if (location.hash === "#register") showForm("register");
        return;
    }
    const facts = [
        [t("username"), user.username],
        [t("display_name"), user.display_name],
        [t("email"), user.email],
        [t("member_since"), new Date(user.created_at).toLocaleDateString(LOCALE)],
    ];
    document.getElementById("account-facts").innerHTML = facts.map(([k, v]) =>
        `<dt class="col-sm-4 text-body-secondary">${esc(k)}</dt><dd class="col-sm-8">${esc(v)}</dd>`).join("");
    document.getElementById("logout").onclick = async () => {
        await api("/api/auth/logout");
        location.assign("/");
    };
    document.getElementById("logged-in").classList.remove("d-none");

    const mine = await fetch("/api/listings/mine").then(r => r.json()).catch(() => []);
    document.getElementById("my-listings-grid").innerHTML = mine.map(l => listingCard(l, { showSeller: false })).join("");
    document.getElementById("my-listings-empty").classList.toggle("d-none", mine.length > 0);
    document.getElementById("my-listings").classList.remove("d-none");
}

applyI18n();
renderAccountArea();
load();
