# Knowledge base

Why SaveOnGames is built the way it is, the words it uses, and how its parts fit. What each module does is in its own docstring; these pages hold the rest.

## Start here

- **[Architecture](architecture.md)**: the whole system on one page. Read it before your first change to a part you don't know.
- **[Glossary](../GLOSSARY.md)**: the project's terms, and the words to avoid. Read it before naming anything.

## Decisions

- **[adr/](adr/)**: one file per decision. Read the ones that touch the area you're changing before you change how it works.

## Running and deploying

- **[README.md](../README.md)**: setup with Docker or on Windows, the API, tests, adding a store.
- **[DEPLOY.md](../DEPLOY.md)**: the server, updates and backups.

## Rules for agents

- **[agents/](agents/)**: Python and frontend rules, the issue tracker and its labels. [AGENTS.md](../AGENTS.md) says when to read each.

## Adding to it

- **Write** the why and the terms. What the code does belongs in the code's docstrings.
- **A decision** that affects one place stays as a `(user, YYYY-MM-DD)` comment beside the code. One that spans modules, or that someone might undo without knowing why, becomes an ADR: the next number in `docs/adr/`, as `NNNN-short-title.md`.
- **A new term** goes in the glossary, with the words to avoid.
- **Paths**: `tests/test_docs.py` fails when a page here names a file or folder that doesn't exist.
