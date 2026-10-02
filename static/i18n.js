/*
 * Portuguese / English for both pages.
 * - t("key", {vars}) for text built in JavaScript
 * - data-i18n="key" (text), data-i18n-placeholder / -aria-label / -title for fixed HTML
 * The choice is remembered in this browser; the first visit follows the browser's language.
 * Store descriptions and game / edition names come from the stores and are not translated.
 */
const STRINGS = {
    pt: {
        // header & search
        home: "🏠 Início",
        dark_mode: "Modo escuro",
        language: "Idioma",
        search_placeholder: "Ex: resident evil",
        all_platforms: "Todas as plataformas",
        platform: "Plataforma",
        search: "Pesquisar",
        no_results: "Nenhum jogo encontrado.",

        // tabs
        tab_discounts: "🔥 Descontos e melhores preços",
        tab_preorders: "📦 Pré-reservas",
        tab_releases: "📅 Calendário de lançamentos",
        tab_catalog: "📚 Catálogo",
        tab_special: "💎 Edições especiais",
        tab_favorites: "⭐ Favoritos",
        empty_discounts: "Ainda sem descontos para mostrar. Só contam descontos reais: o preço tem de estar abaixo do mais baixo dos 30 dias anteriores, por isso os primeiros aparecem após um mês de histórico.",
        empty_preorders: "Sem jogos em pré-reserva de momento.",
        empty_releases: "Ainda sem datas de lançamento anunciadas.",
        empty_catalog: "Sem jogos em stock para esta plataforma.",
        empty_special: "Sem edições especiais em stock para esta plataforma.",
        empty_favorites: "Ainda não tens favoritos. Carrega na ☆ de um jogo para o acompanhares aqui.",
        empty_platform: "Nada para esta plataforma.",
        store_deals_intro: "<strong>Melhores preços entre lojas.</strong> Ainda não há descontos reais para mostrar (o preço tem de estar abaixo do mais baixo dos 30 dias anteriores, e o histórico começou a 1 de outubro). Entretanto, estes jogos estão bem mais baratos numa loja do que na seguinte.",
        vs_other_stores: "-{percent}% vs outras lojas",

        // cards
        view_at: "Ver na {store}",
        used: "Usado",
        sold_out: "Esgotado",
        in_stock: "Em stock",
        new: "Novo",
        preorder: "Pré-reserva",
        favorite: "Favorito",
        see_all_stores: "Ver todas as lojas (+{count})",
        no_offers: "Sem ofertas de momento",
        back_in_stock: "🔔 De volta ao stock",
        lowest_ever: "★ Preço mais baixo de sempre",
        historical_low_short: "Mínimo histórico: {price}",
        date_tba: "Data por anunciar",
        date_tba_year: "Data por anunciar ({year})",
        editions_count: "{count} edições",
        today: "Hoje",

        // catalogue
        catalog_count: "{count} edições em stock · página {page} de {pages}",
        special_count: "{count} edições especiais em stock · página {page} de {pages}",
        sort: "Ordenar:",
        sort_name: "Nome (A–Z)",
        sort_price_asc: "Preço: mais barato primeiro",
        sort_price_desc: "Preço: mais caro primeiro",
        pages: "Páginas",
        previous: "« Anterior",
        next: "Seguinte »",

        // alerts & store status
        restock_one: "Um favorito voltou ao stock",
        restock_many: "{count} favoritos voltaram ao stock",
        dismiss: "Dispensar",
        view_in_store: "Ver na loja",
        status_intro: "Preços das lojas, atualizados uma vez por dia:",
        updated_ago: "atualizado {ago}",
        never_updated: "nunca atualizado",
        ago_less_hour: "há menos de 1 h",
        ago_hours: "há {count} h",
        ago_days: "há {count} dias",
        status_failed: "a última atualização falhou",
        status_warning: "a última atualização teve um problema",
        status_stale: "desatualizada",

        // game page
        back: "← Voltar",
        back_search: "← Pesquisa",
        game_not_found: "Jogo não encontrado.",
        game_load_error: "Não foi possível carregar o jogo.",
        release_on: "Lançamento: {date}",
        release_tba: "Lançamento: data por anunciar ({year})",
        tracked_since: "Preços acompanhados desde {date}. O mínimo histórico conta só cópias novas em stock.",
        about: "Sobre o jogo",
        store_description: "Descrição da {store}",
        igdb_summary: "Resumo do IGDB (em inglês)",
        igdb_summary_short: "Resumo do IGDB",
        store_description_pt: "Descrição da {store} (em português)",
        screenshot: "Imagem do jogo",
        videos: "Vídeos",
        play_video: "Ver o vídeo: {name}",
        video_source: "Vídeos do YouTube, via IGDB. O leitor só carrega quando escolhe um vídeo.",
        photos_from: "Fotografias da {store}",
        photo: "Fotografia da edição",
        read_more: "Ler mais",
        read_less: "Ler menos",
        publisher: "Editora",
        developer: "Produtora",
        released: "Lançamento",
        rating: "Classificação",
        whats_included: "O que inclui",
        according_to: "Segundo a {store} (em português)",
        digital_code: "⚠ Jogo em código digital (sem disco)",
        digital_code_hint: "Segundo a descrição da loja, o jogo vem em código de download",
        best_price_now: "Melhor preço agora:",
        historical_low: "★ Mínimo histórico:",
        lowest_ever_now: "Preço mais baixo de sempre",
        period: "Período",
        days_30: "30 dias",
        days_90: "90 dias",
        year_1: "1 ano",
        all_time: "Tudo",
        price_history: "Histórico de preços",
        new_copies: "(cópias novas)",
        price_history_of: "Histórico de preços de {name}",
        dashed_sold_out: "Linha tracejada: esgotado nesse período.",
        history_table: "Ver histórico em tabela",
        no_history: "Sem histórico.",
        col_store: "Loja",
        col_condition: "Estado",
        col_price: "Preço",
        col_stock: "Stock",
        col_date: "Data",
        chart_low: "Mínimo histórico {price}",
        chart_sold_out: "(esgotado)",
        chart_current: "(atual)",
    },
    en: {
        home: "🏠 Home",
        dark_mode: "Dark mode",
        language: "Language",
        search_placeholder: "E.g. resident evil",
        all_platforms: "All platforms",
        platform: "Platform",
        search: "Search",
        no_results: "No games found.",

        tab_discounts: "🔥 Discounts and best prices",
        tab_preorders: "📦 Pre-orders",
        tab_releases: "📅 Release calendar",
        tab_catalog: "📚 Catalogue",
        tab_special: "💎 Special editions",
        tab_favorites: "⭐ Favourites",
        empty_discounts: "No discounts to show yet. Only real discounts count: the price must be below the lowest of the previous 30 days, so the first ones appear after a month of price history.",
        empty_preorders: "No games on pre-order right now.",
        empty_releases: "No release dates announced yet.",
        empty_catalog: "No games in stock for this platform.",
        empty_special: "No special editions in stock for this platform.",
        empty_favorites: "No favourites yet. Click the ☆ on a game to follow it here.",
        empty_platform: "Nothing for this platform.",
        store_deals_intro: "<strong>Best prices between stores.</strong> There are no real discounts to show yet (the price must be below the lowest of the previous 30 days, and price tracking started on 1 October). Meanwhile, these games are much cheaper at one store than at the next.",
        vs_other_stores: "-{percent}% vs other stores",

        view_at: "View at {store}",
        used: "Used",
        sold_out: "Sold out",
        in_stock: "In stock",
        new: "New",
        preorder: "Pre-order",
        favorite: "Favourite",
        see_all_stores: "See all stores (+{count})",
        no_offers: "No offers right now",
        back_in_stock: "🔔 Back in stock",
        lowest_ever: "★ Lowest price ever",
        historical_low_short: "Historical low: {price}",
        date_tba: "Date to be announced",
        date_tba_year: "Date to be announced ({year})",
        editions_count: "{count} editions",
        today: "Today",

        catalog_count: "{count} editions in stock · page {page} of {pages}",
        special_count: "{count} special editions in stock · page {page} of {pages}",
        sort: "Sort:",
        sort_name: "Name (A–Z)",
        sort_price_asc: "Price: lowest first",
        sort_price_desc: "Price: highest first",
        pages: "Pages",
        previous: "« Previous",
        next: "Next »",

        restock_one: "A favourite is back in stock",
        restock_many: "{count} favourites are back in stock",
        dismiss: "Dismiss",
        view_in_store: "View in store",
        status_intro: "Store prices, updated once a day:",
        updated_ago: "updated {ago}",
        never_updated: "never updated",
        ago_less_hour: "less than 1 h ago",
        ago_hours: "{count} h ago",
        ago_days: "{count} days ago",
        status_failed: "the last update failed",
        status_warning: "the last update had a problem",
        status_stale: "out of date",

        back: "← Back",
        back_search: "← Search",
        game_not_found: "Game not found.",
        game_load_error: "The game could not be loaded.",
        release_on: "Release: {date}",
        release_tba: "Release: date to be announced ({year})",
        tracked_since: "Prices tracked since {date}. The historical low only counts new copies in stock.",
        about: "About the game",
        store_description: "Description by {store}",
        igdb_summary: "Summary from IGDB",
        igdb_summary_short: "Summary from IGDB",
        store_description_pt: "Description by {store} (in Portuguese)",
        screenshot: "Game screenshot",
        videos: "Videos",
        play_video: "Play video: {name}",
        video_source: "YouTube videos, via IGDB. The player only loads when you pick a video.",
        photos_from: "Photos from {store}",
        photo: "Photo of the edition",
        read_more: "Read more",
        read_less: "Read less",
        publisher: "Publisher",
        developer: "Developer",
        released: "Released",
        rating: "Rating",
        whats_included: "What's included",
        according_to: "According to {store} (in Portuguese)",
        digital_code: "⚠ Game as a download code (no disc)",
        digital_code_hint: "According to the store's description, the game comes as a download code",
        best_price_now: "Best price now:",
        historical_low: "★ Historical low:",
        lowest_ever_now: "Lowest price ever",
        period: "Period",
        days_30: "30 days",
        days_90: "90 days",
        year_1: "1 year",
        all_time: "All",
        price_history: "Price history",
        new_copies: "(new copies)",
        price_history_of: "Price history of {name}",
        dashed_sold_out: "Dashed line: sold out during that period.",
        history_table: "Show history as a table",
        no_history: "No history.",
        col_store: "Store",
        col_condition: "Condition",
        col_price: "Price",
        col_stock: "Stock",
        col_date: "Date",
        chart_low: "Historical low {price}",
        chart_sold_out: "(sold out)",
        chart_current: "(current)",
    },
};

function savedLanguage() {
    let lang = null;
    try { lang = localStorage.getItem("lang"); } catch (e) {}
    if (STRINGS[lang]) return lang;
    return (navigator.language || "pt").toLowerCase().startsWith("pt") ? "pt" : "en";
}

const LANG = savedLanguage();
const LOCALE = LANG === "pt" ? "pt-PT" : "en-GB";
const eur = new Intl.NumberFormat(LOCALE, { style: "currency", currency: "EUR" });

function t(key, vars = {}) {
    const text = STRINGS[LANG][key] ?? STRINGS.pt[key] ?? key;
    return text.replace(/\{(\w+)\}/g, (_, name) => vars[name] ?? "");
}

function fmtNumber(n) {
    return Number(n).toLocaleString(LOCALE);
}

// Fixed HTML: data-i18n="key" sets the text; data-i18n-placeholder / -aria-label / -title the attribute
function applyI18n(root = document) {
    document.documentElement.lang = LANG;
    root.querySelectorAll("[data-i18n]").forEach(el => el.textContent = t(el.dataset.i18n));
    const attributes = { placeholder: "i18nPlaceholder", "aria-label": "i18nAriaLabel", title: "i18nTitle" };
    for (const [attr, key] of Object.entries(attributes)) {
        root.querySelectorAll(`[data-i18n-${attr}]`).forEach(el => el.setAttribute(attr, t(el.dataset[key])));
    }
    renderLanguageSwitch();
}

// PT | EN buttons in the header (solid, the current one in blue). Switching reloads the page.
function renderLanguageSwitch() {
    const box = document.getElementById("lang-switch");
    if (!box) return;
    box.innerHTML = ["pt", "en"].map(lang =>
        `<button type="button" class="btn btn-sm ${lang === LANG ? "btn-primary" : "btn-secondary"}"
            data-lang="${lang}" aria-pressed="${lang === LANG}">${lang.toUpperCase()}</button>`).join("");
    box.querySelectorAll("[data-lang]").forEach(b => b.onclick = () => {
        if (b.dataset.lang === LANG) return;
        try { localStorage.setItem("lang", b.dataset.lang); } catch (e) {}
        location.reload();
    });
}
