#!/bin/sh
# Container start: create / update the database (waiting for PostgreSQL to be up), load the
# demo data the first time if the file is there, then serve the site on port 5000.
set -e

DEMO=/app/database/demo/demo.json.gz
if [ -f "$DEMO" ]; then
    python -m database.setup --wait 120 --demo "$DEMO"
else
    python -m database.setup --wait 120
    echo "No demo data ($DEMO): the site starts empty. See README.md, 'Try it with Docker'."
fi

exec waitress-serve --host=0.0.0.0 --port=5000 app.web:app
