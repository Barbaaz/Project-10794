# Running the real site on a server

The site, its database, the daily scraper runs and backups on one rented server, so nothing
depends on the PC being on. It uses `docker-compose.production.yml` on top of `docker-compose.yml`:

```
visitors ──HTTPS──> Caddy ──> site (web) ──> PostgreSQL (db) <── scheduler (06:00 / 18:00 runs, IGDB)
                                                    └── backup (03:30: database + photos → ./backups)
```

**Cost:** about €5–6 a month at Hetzner (the smallest server with 4 GB, plus its IPv4 address),
billed by the hour until the server is deleted. **Time:** about an hour the first time.

**You need:** this repository on GitHub with the code you want to run (`main`), a card or PayPal
for Hetzner, and for moving the real data: PostgreSQL's tools on the PC (installed with PostgreSQL).

Commands marked **PC** go in PowerShell on your computer; **server** ones in the SSH window.
`203.0.113.5` stands for your server's address throughout.

---

## 1. An SSH key (once per computer)

**PC:**

```powershell
ssh-keygen -t ed25519          # Enter three times (default place, no passphrase) or set a passphrase
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub     # copy this whole line for step 2
```

If you already have `id_ed25519.pub`, skip `ssh-keygen` and only show it.

## 2. The server

1. Log in to <https://console.hetzner.cloud> (create an account if needed; ID verification can take
   a few hours the first time).
2. **New project** (e.g. "Produção") → **Add Server**:
   - **Location:** any in Europe (Nuremberg, Falkenstein or Helsinki)
   - **Image:** Ubuntu 24.04
   - **Type:** Shared vCPU, the smallest with **4 GB of memory** (x86 CX23 or Arm CAX11)
   - **Networking:** Public IPv4 on (IPv6 too)
   - **SSH keys:** **Add SSH key** → paste the line from step 1
   - **Firewalls:** **Create Firewall** with inbound TCP **22**, **80**, **443** (any IPv4 / IPv6),
     applied to this server
   - **Backups:** on (+20% of the price): Hetzner keeps 7 daily copies of the whole server, a
     second safety net besides the nightly backups below
   - **Name:** e.g. `precos`
3. **Create & Buy now**. Note the server's **IPv4 address**.

A separate server from the testers' copy (HOSTING.md on `testers`): both need ports 80 and 443.

## 3. Connect and install Docker

**PC:** `ssh root@203.0.113.5` (answer "yes" the first time). **Server:**

```bash
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh
docker compose version        # prints a version: Docker is ready
timedatectl set-timezone Europe/Lisbon    # only for the times in your terminal; the runs use Lisbon time anyway
```

If `apt upgrade` says a restart is needed: `reboot`, wait a minute and `ssh` in again.

## 4. The code and the settings

**Server:**

```bash
git clone https://github.com/Barbaaz/Project-10794.git
cd Project-10794
mkdir -p instance/uploads logs backups
printf "COMPOSE_FILE=docker-compose.yml:docker-compose.production.yml\nDB_PASSWORD=Db%s\nSECRET_KEY=%s\nDOMAIN=%s\n" \
  "$(openssl rand -hex 12)" "$(openssl rand -hex 32)" "$(hostname -I | awk '{print $1}' | tr . -).sslip.io" > .env
chmod 600 .env
nano .env
```

`COMPOSE_FILE` makes every `docker compose` command use the production setup. In `nano`, add what
you have (Ctrl+O, Enter saves; Ctrl+X leaves):

```
IGDB_CLIENT_ID=...                  # new games' information (the same as on the PC)
IGDB_CLIENT_SECRET=...
STEAM_API_KEY=...                   # /collection's Steam import (the same as on the PC)
SMTP_HOST=...                       # e-mail: password reset, and alerts when a store fails
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
MAIL_FROM=...
ALERT_EMAIL=your@address
```

Without SMTP the site works, but e-mails are only written to the log (nobody gets a password
reset link) and a failing store only shows as ⚠ in the front page footer.

**`DOMAIN`**: the site's address. Without a domain of your own it's `203-0-113-5.sslip.io` (a free
service: that name points to `203.0.113.5`). With a domain: add an A record pointing to the server,
put the name here, and `docker compose up -d` again (Caddy gets the new certificate by itself).

## 5. Move the real data from the PC

Do this in one go: from step 1 below until the site runs on the server, the PC no longer scrapes.

1. **PC:** stop the PC's daily runs, for good (two copies scraping would double the requests to
   the stores, and the PC's database is no longer the real one):

   ```powershell
   Disable-ScheduledTask -TaskName Project10794-Scrapers, Project10794-Scrapers-Evening
   ```

   Also stop `python app.py` if it's running, so nobody changes the PC's data after the copy.

2. **PC:** copy the database to a file, then send it and the listings' photos to the server:

   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -h localhost -U project10794 -d project10794 -Fc -f C:\Dev\project10794-move.dump
   scp C:\Dev\project10794-move.dump root@203.0.113.5:/root/Project-10794/backups/
   scp -r C:\Dev\Project-10794\instance\uploads root@203.0.113.5:/root/Project-10794/instance/
   ```

3. **Server:** start only the database and load the copy into it:

   ```bash
   cd ~/Project-10794
   docker compose up -d db
   sleep 10
   docker compose exec -T db pg_restore -U project10794 -d postgres --create --no-owner < backups/project10794-move.dump
   ```

   It prints nothing when all went well.

## 6. Start

**Server:**

```bash
docker compose up -d --build
docker compose logs -f web     # wait for "Serving on http://0.0.0.0:5000", then Ctrl+C
docker compose logs scheduler  # "Next run: … 06:00" or "… 18:00"
```

Open **https://203-0-113-5.sslip.io** (your `DOMAIN`). Log in with your account as on the PC:
everything (games, prices, accounts, listings with photos) is there. If the browser says the
connection isn't secure, Caddy is still getting the certificate: `docker compose logs caddy` says
why (usually ports 80 / 443 missing from the firewall).

Then make a first backup and check it:

```bash
docker compose exec backup sh /backup.sh --now
ls -lh backups
```

## 7. Watch the first runs

The stores now see requests from a data centre instead of a home connection, and may treat them
differently. After the first 06:00 and 18:00 runs:

```bash
grep -E "WARNING|ERROR|403|429| done:" logs/scraper-$(date +%F).log | tail -40
```

Every store should end with `done:` and no 403 / 429. The scrapers already stop at the first 403 /
429 and the run is marked failed (⚠ in the footer, e-mail with `ALERT_EMAIL`). If a store blocks the
server: don't work around it; switch that store off and decide what to do:
`docker compose exec db psql -U project10794 -c "UPDATE stores SET is_active = false WHERE slug = 'cstech'"`.

---

## Looking after it

All on the **server**, in `~/Project-10794`:

| To... | Run |
|-------|-----|
| See whether it's running | `docker compose ps` |
| The site's log | `docker compose logs --tail 100 web` |
| The scraper runs' log | `tail -100 logs/scraper-$(date +%F).log` (one file per day, kept 30 days) |
| Run one store by hand (gently: the 8 h gap applies) | `docker compose exec scheduler python -m scheduler.run_single_store press_start` |
| Make someone a moderator / admin | `docker compose exec web python -m database.users role <username> moderator` |
| Open the database | `docker compose exec db psql -U project10794` |
| Stop it for a while | `docker compose stop` (`docker compose start` to resume; still billed) |

It starts again by itself after a server restart (a run that was due while it was off is skipped).

### Updating to newer code

Push the new code to `main` on GitHub first. Then, **server:**

```bash
cd ~/Project-10794
docker compose exec backup sh /backup.sh --now   # a backup just before, in case
git pull
docker compose up -d --build
docker compose logs -f web     # wait for "Serving on http://0.0.0.0:5000", then Ctrl+C
docker image prune -f          # old images the rebuild left behind
```

New tables and columns are added by the site itself at start (`database.setup`, Alembic). Avoid
updating while a run is going (06:00–~06:50, 18:00–~18:20): the rebuild restarts the scheduler,
and the run in progress stops.

If the site doesn't come back: `docker compose logs --tail 100 web` says why. To go back:
`git log --oneline -5`, `git checkout <the commit before>`, `docker compose up -d --build`
(`git checkout main` returns to the newest code afterwards).

### Backups

Every night at 03:30: `backups/project10794-<date>.dump` (the database, kept 14 days) and
`backups/uploads-<date>.tar.gz` (the photos, last 3). They're on the same server, so also copy
them off it now and then. **PC:**

```powershell
scp "root@203.0.113.5:/root/Project-10794/backups/project10794-*.dump" C:\Dev\backups\
```

(the newest is enough; `ssh root@203.0.113.5 ls -t Project-10794/backups` lists them).

**Restoring** a dump (replaces everything since it was made). **Server:**

```bash
docker compose stop web scheduler
docker compose exec -T db pg_restore -U project10794 -d postgres --clean --create --no-owner < backups/project10794-<date>.dump
docker compose start web scheduler
```

Photos: `tar -xzf backups/uploads-<date>.tar.gz -C instance/uploads`.

**On the PC** (to look at the real data there, e.g. to try a change): the same `pg_restore` into
the PC's PostgreSQL, after renaming or dropping the old database. Never turn the PC's daily
tasks back on while the server runs.

## Stopping for good

Copy the last backup to the PC (above), then in the Hetzner console: the server → **Delete**.
To run on the PC again: restore that dump on the PC and `Enable-ScheduledTask` the two tasks.
