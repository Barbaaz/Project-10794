// Contactos (templates/contact.html; user, 2026-10-16): a message to the site's team (contact_service).
// Logged in: the name and e-mail come from the account (the e-mail can be changed: replies go there)
const form = document.getElementById("contact-form");
const count = () => document.getElementById("contact-count").textContent =
    t("contact_count", { n: fmtNumber(form.body.value.length), max: fmtNumber(4000) });

async function load() {
    document.title = `${t("contact_title")} · SaveOnGames`;
    await renderAccountArea();
    if (currentUser) {
        form.name.value = currentUser.display_name || currentUser.username || "";
        form.email.value = currentUser.email || "";
    }
    const topic = new URLSearchParams(location.search).get("topic");      // e.g. /contact?topic=store
    if ([...form.topic.options].some(o => o.value === topic)) form.topic.value = topic;
    count();
}

form.body.oninput = count;
form.onsubmit = async event => {
    event.preventDefault();
    const error = document.getElementById("contact-error"), button = form.querySelector("[type=submit]");
    error.textContent = "";
    const body = Object.fromEntries(["name", "email", "topic", "body", "website"].map(k => [k, form[k].value]));
    button.disabled = true;
    const { ok, data } = await api("/api/contact", { body });
    button.disabled = false;
    if (!ok) {
        error.textContent = t(`error_${data?.error || "unknown"}`);
        const field = { contact_name_invalid: "name", email_invalid: "email", contact_body_short: "body", contact_body_long: "body" }[data?.error];
        if (field) form[field].focus();
        return;
    }
    form.classList.add("d-none");
    const done = document.getElementById("contact-done");
    done.classList.remove("d-none");
    done.focus();
};

applyI18n();
load();
