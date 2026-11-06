# SaveOnGames

Compares the prices Portuguese stores charge for games, and adds a pre-owned marketplace and game collections. Built with Flask, SQLAlchemy and PostgreSQL. The site is in Portuguese and English; code and comments are in English.

The daily run (`scheduler/`) writes the prices. The web app (`app/`) reads them and writes only what people do on the site.

## Read before working

- **Python**: before writing or reviewing `.py` in `app/`, `scrapers/`, `pipeline/`, `core/`, `scheduler/`, `database/` or `migrations/` → [docs/agents/python.md](docs/agents/python.md)
- **Frontend**: before editing `templates/` or `static/` → [docs/agents/html.md](docs/agents/html.md)
- **Domain**: before naming a concept or making an architecture decision → [docs/agents/domain.md](docs/agents/domain.md)
- **Issues**: before creating, reading or labelling a GitHub issue → [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md), with labels in [docs/agents/triage-labels.md](docs/agents/triage-labels.md)

## Checking work

`python -m pytest` (README.md has the Docker form).
