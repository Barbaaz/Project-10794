#!/bin/sh
# Container start: create / update the database (waiting for PostgreSQL to be up), load the
# demo data the first time if the file is there, then serve the site on port 5000.
# DEMO_MODE=1 (the teste/ launchers): also the made-up marketplace users the first time, with
# demo_eva as a moderator so testers can see the moderators' page.
set -e

DEMO=/app/database/demo/demo.json.gz
# Safari unpacks .gz files on download
[ -f "$DEMO" ] || [ ! -f /app/database/demo/demo.json ] || DEMO=/app/database/demo/demo.json
if [ -f "$DEMO" ]; then
    python -m database.setup --wait 120 --demo "$DEMO"
    if [ "$DEMO_MODE" = "1" ]; then
        python -m database.demo_market --if-missing
        python -m database.users role demo_eva moderator
    fi
else
    python -m database.setup --wait 120
    echo "No demo data ($DEMO): the site starts empty. See README.md, 'Try it with Docker'."
fi

exec waitress-serve --host=0.0.0.0 --port=5000 app.web:app
