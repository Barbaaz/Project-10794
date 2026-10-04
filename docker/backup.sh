#!/bin/sh
# Nightly backup on the server (docker-compose.production.yml, "backup" service, postgres:18
# image so pg_dump matches the server): at 03:30 Lisbon time, the database (pg_dump custom format,
# restored with pg_restore) and the uploaded photos, into ./backups on the server. Database dumps
# are kept 14 days, photo archives 3 (each holds every photo). DEPLOY.md says how to copy them off
# the server. Run once now: docker compose exec backup sh /backup.sh --now
set -e

backup() {
    stamp=$(date +%Y%m%d-%H%M)
    pg_dump -h db -U project10794 -d project10794 -Fc -f "/backups/project10794-$stamp.dump.part"
    mv "/backups/project10794-$stamp.dump.part" "/backups/project10794-$stamp.dump"
    tar -czf "/backups/uploads-$stamp.tar.gz.part" -C /uploads .
    mv "/backups/uploads-$stamp.tar.gz.part" "/backups/uploads-$stamp.tar.gz"
    find /backups -name 'project10794-*.dump' -mtime +13 -delete
    ls -1t /backups/uploads-*.tar.gz | tail -n +4 | xargs -r rm --
    echo "$(date '+%F %T') backup done: project10794-$stamp.dump, uploads-$stamp.tar.gz"
}

if [ "$1" = "--now" ]; then
    backup
    exit
fi

while true; do
    next=$(date -d 'today 03:30' +%s)
    [ "$next" -gt "$(date +%s)" ] || next=$(date -d 'tomorrow 03:30' +%s)
    sleep $((next - $(date +%s)))
    backup || echo "$(date '+%F %T') backup FAILED"
done
