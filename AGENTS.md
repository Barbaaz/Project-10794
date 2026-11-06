# SaveOnGames

Compares the prices Portuguese stores charge for games, and adds a pre-owned marketplace and game collections. Built with Flask, SQLAlchemy and PostgreSQL. The site is in Portuguese and English; code and comments are in English.

The daily run (`scheduler/`) writes the prices. The web app (`app/`) reads them and writes only what people do on the site.

## Read before working

- **Knowledge base**: before changing how a part works, or when a term, a past decision or the architecture is unclear → [docs/README.md](docs/README.md)
- **Python**: before writing or reviewing `.py` in `app/`, `scrapers/`, `pipeline/`, `core/`, `scheduler/`, `database/` or `migrations/` → [docs/agents/python.md](docs/agents/python.md)
- **Frontend**: before editing `templates/` or `static/` → [docs/agents/html.md](docs/agents/html.md)
- **Domain**: before naming a concept or making an architecture decision → [docs/agents/domain.md](docs/agents/domain.md)
- **Issues**: before creating, reading or labelling a GitHub issue → [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md), with labels in [docs/agents/triage-labels.md](docs/agents/triage-labels.md)

## Structure

```
app.py                     development server: python app.py → http://127.0.0.1:5000
db.py                      database access: session() (SQLAlchemy), fetch_all / fetch_one (psycopg pool)
app/
  web.py                   the Flask app: page routes, request guards, security headers
  config.py                settings read from environment variables (.env.example lists them)
  models.py                SQLAlchemy models for every table
  routes/                  the JSON API, one blueprint per area (/api/…)
  services/                the rules, one module per area; routes call these
  utils/utils.py           which platform a store's product name is for
  data/                    common passwords refused at sign-up
core/                      name rules: editions, normalising, close matches, consoles, titles
scrapers/
  base/                    BaseScraper, ShopifyScraper, the polite HttpClient, robots.txt rules
  <store>/                 one package per store: scraper.py, parser.py, selectors.py
pipeline/                  scraped products → games, editions, prices; IGDB; rematch
scheduler/                 the daily runs: run_all_scrapers, run_single_store, daemon, Windows task
database/
  *.sql                    price side: schema, indexes, views, stores
  setup.py                 creates or updates the database (the SQL files, then Alembic)
  demo.py, demo_market.py  demo catalogue and demo marketplace
  users.py                 account roles from the command line
  from_sqlserver.py        the one-time copy from the old SQL Server database
migrations/versions/       Alembic revisions for the marketplace tables
templates/                 Jinja pages; _header.html and _footer.html are on every page
static/
  pages/                   one script per page
  common.js, common.css    shared script (api, esc, account area, theme) and styles
  i18n.js                  every text, in pt and en
  market.js                marketplace pieces several pages use
  sw.js, manifest.webmanifest, offline.html   the installable app and its offline page
tests/                     pytest; fixtures/ holds saved store pages
docker/                    container start, nightly backup, Caddy config for HTTPS
docs/                      knowledge base: README.md (its index), architecture.md, adr/, how-to/
  agents/                  these rules
Dockerfile, docker-compose.yml, docker-compose.production.yml
GLOSSARY.md                the project's terms
README.md, DEPLOY.md       local setup and server deployment
```

Created when the app runs, not in git: `instance/uploads/` (photos), `logs/`, `backups/`.

## Checking work

`python -m pytest` (README.md has the Docker form).
