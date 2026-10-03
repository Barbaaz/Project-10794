# Hosting a test copy online

A copy of the site on a rented server, so testers only need a link and a password (nothing to
install). It runs the same Docker setup as `teste/`, in demo mode (the demo data, no scraping), with
[Caddy](https://caddyserver.com/) in front for HTTPS and **one shared password for the whole site**
(the store descriptions in the demo data aren't ours to publish, and nobody else should be able to
sign up or upload photos).

```
tester's browser ──HTTPS + password──> Caddy ──> site (web) ──> SQL Server (db)      all on one server
```

**Cost:** about €5 a month at Hetzner, billed by the hour until the server is **deleted** (a server
that is only switched off is still billed). **Time:** about 45 minutes the first time.

**You need:** the `testers` branch on GitHub (it holds `docker-compose.hosting.yml`), the demo data
file (`C:\Dev\Project-10794-testers\database\demo\demo.json.gz`), and a card or PayPal for Hetzner.

Commands marked **PC** go in PowerShell on your computer; commands marked **server** go in the SSH
window connected to the server.

---

## 1. An SSH key (once per computer)

The key lets you log in to the server without a password. **PC:**

```powershell
ssh-keygen -t ed25519          # Enter three times (default place, no passphrase) or set a passphrase
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub     # copy this whole line for step 2
```

If you already have `id_ed25519.pub`, skip `ssh-keygen` and only show it.

## 2. The server

1. Create an account at <https://console.hetzner.cloud> (they may ask for ID verification; it can
   take a few hours the first time).
2. **New project** → open it → **Add Server**:
   - **Location:** any in Europe (Nuremberg, Falkenstein or Helsinki)
   - **Image:** Ubuntu 24.04
   - **Type:** Shared vCPU → **x86** (Intel / AMD), the smallest with **4 GB of memory** (CX22 or the
     type that replaced it). **Not Arm (CAX)**: SQL Server only runs on x86
   - **Networking:** Public IPv4 on (IPv6 too)
   - **SSH keys:** **Add SSH key** → paste the line from step 1
   - **Firewalls:** **Create Firewall** with these inbound rules: TCP **22**, TCP **80**, TCP **443**
     (any IPv4 / IPv6). Apply it to this server
   - **Name:** e.g. `teste-precos`
3. **Create & Buy now**. Note the server's **IPv4 address** (e.g. `203.0.113.5`).

## 3. Connect and install Docker

**PC:**

```powershell
ssh root@203.0.113.5          # your server's address; answer "yes" the first time
```

**Server** (updates, then Docker from Docker's own install script):

```bash
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh
docker compose version        # should print a version: Docker is ready
```

If `apt upgrade` says a restart is needed: `reboot`, wait a minute and `ssh` in again.

## 4. The code and the demo data

**Server:**

```bash
git clone -b testers https://github.com/Barbaaz/Project-10794.git
mkdir -p Project-10794/database/demo
```

**PC** (in a second PowerShell window; the server's address again):

```powershell
scp C:\Dev\Project-10794-testers\database\demo\demo.json.gz root@203.0.113.5:/root/Project-10794/database/demo/
```

## 5. Settings: address and password

The site needs an address for its HTTPS certificate. Without a domain of your own, use
**sslip.io**, a free service where `203-0-113-5.sslip.io` points to `203.0.113.5`. (With your own
domain, add an A record pointing to the server and put that name in `DOMAIN` below.)

**Server** (change only the password on the first line; testers will type it):

```bash
cd ~/Project-10794
TEST_PASSWORD='choose-a-password-for-testers'
HASH=$(docker run --rm caddy:2-alpine caddy hash-password --plaintext "$TEST_PASSWORD")
printf "COMPOSE_FILE=docker-compose.yml:docker-compose.hosting.yml\nDB_PASSWORD=Db-%s-Aa1\nSECRET_KEY=%s\nDOMAIN=%s\nTEST_USER=teste\nTEST_PASSWORD_HASH='%s'\n" \
  "$(openssl rand -hex 8)" "$(openssl rand -hex 32)" "$(hostname -I | awk '{print $1}' | tr . -).sslip.io" "$HASH" > .env
chmod 600 .env
grep DOMAIN .env               # the site's address, e.g. DOMAIN=203-0-113-5.sslip.io
```

`.env` keeps the passwords on the server only (only a scrambled form of the testers' password).
`COMPOSE_FILE` makes every `docker compose` command below use the hosting setup.

## 6. Start

**Server:**

```bash
docker compose up -d --build
docker compose logs -f web     # wait for "Serving on http://0.0.0.0:5000", then Ctrl+C
```

The first start takes a few minutes (building, SQL Server, loading the demo data and demo users).
Open **https://203-0-113-5.sslip.io** (your `DOMAIN`): the browser asks for a user name and
password → `teste` and the password from step 5. The blue "Versão de teste" banner should show.

If the browser says the connection isn't secure, Caddy is still getting the certificate:
`docker compose logs caddy` shows why (usually ports 80 / 443 missing from the firewall in step 2).

## 7. Tell the testers

Send them the link, the user name `teste` and the password, and the guide `GUIA-DE-TESTE.md`
(they start at **Passo 5**, "O que testar"; steps 1–4 are only for running it on their own computer).
For example:

> Olá! Pode testar o site em https://203-0-113-5.sslip.io (utilizador: teste, palavra-passe: …).
> O que experimentar e como enviar o que encontrar está no guia, a partir do passo 5:
> https://github.com/Barbaaz/Project-10794/blob/testers/GUIA-DE-TESTE.md

---

## Looking after it

All on the **server**, in `~/Project-10794` (`ssh root@203.0.113.5`, then `cd Project-10794`):

| To... | Run |
|-------|-----|
| See whether it's running | `docker compose ps` |
| Read the site's log | `docker compose logs --tail 100 web` |
| Update to newer code pushed to `testers` | `git pull && docker compose up -d --build` |
| Load a newer demo data file | copy it with `scp` (step 4), then the "start over" line below |
| Start over (deletes testers' accounts, listings, messages) | `docker compose down -v && docker compose up -d --build` |
| Change the testers' password | step 5 again (it rewrites `.env`, **including the database password**, so follow it with "start over") |
| Stop it for a while | `docker compose stop` (`docker compose start` to resume; still billed) |

It starts again by itself if the server restarts. Ubuntu installs security updates by itself.

## When testing is over

In the Hetzner console: the server → **Delete**. Billing stops, and everything on it (data, `.env`)
is gone. Delete the firewall too if you won't reuse it.

## What this copy is not

- It doesn't scrape: prices stay those of the demo file. The daily runs on a server are a separate
  step (the plan's "Hosting" item).
- No e-mails are sent (password reset etc.).
- It's for a closed group: anyone with the shared password can create accounts and upload photos.
  Change the password (step 5 + start over) if it leaks.
