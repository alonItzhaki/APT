# APT — Deployment Runbook

This document covers everything needed to go from a bare VM to a running production instance.

---

## 1. Provision the VM

Use an **Oracle Always-Free ARM** instance: shape `VM.Standard.A1.Flex`, Ubuntu 22.04 or later.
After the instance is up:

1. In the OCI Console → Networking → Security Lists, open inbound ports **80** (HTTP) and **443** (HTTPS).
2. SSH in by key pair:
   ```bash
   ssh ubuntu@<your-vm-ip>
   ```

---

## 2. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

Log out and back in so the group membership takes effect, then verify:

```bash
docker info
```

---

## 3. Deploy

```bash
git clone https://github.com/alonItzhaki/APT.git
cd APT
cp env.example .env
```

Edit `.env` and fill in every required value:

| Variable | Notes |
|---|---|
| `APT_SECRET_KEY` | Generate with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `APT_BASE_URL` | Public HTTPS URL, e.g. `https://apt.example.com` |
| `APT_DOMAIN` | Caddy site address, e.g. `apt.example.com` (enables automatic HTTPS via Let's Encrypt) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google Cloud Console OAuth credentials; set the redirect URI to `$APT_BASE_URL/api/auth/callback` |
| `APT_ADMIN_EMAILS` | Comma-separated list of Google accounts that get admin access |
| `APT_SITE_URL` | Set to the **same** value as `APT_BASE_URL` (`env_file` does not expand `${}` references) |
| `TELEGRAM_BOT_TOKEN` + `APT_BOT_USERNAME` | Optional — only needed for the Telegram channel |
| `BREVO_API_KEY` + `APT_EMAIL_FROM` | Optional — only needed for email alerts |
| `APT_BACKUP_BUCKET` | Optional — OCI Object Storage bucket name for off-box backups |

Start the stack:

```bash
# Without Telegram bot
docker compose up -d --build

# With Telegram bot (TELEGRAM_BOT_TOKEN must be set in .env)
docker compose --profile bot up -d --build
```

Docker Compose will run the `migrate` service first (exits 0 after applying all migrations), then starts `web`, `scraper`, and `caddy` (plus `bot` if the profile is active).

---

## 4. Verification Checklist

Run these checks after every fresh deploy or update:

```bash
# All long-running services up; migrate should show Exited (0)
docker compose ps

# Health endpoint
curl localhost/healthz
# Expected: {"status":"ok"}

# HTTPS + domain
curl https://apt.example.com/healthz
```

Then in a browser:

- **Site loads** over the domain with a valid HTTPS certificate.
- **Sign-in round-trip** — click "Sign in with Google", complete OAuth, land back on the dashboard.
- **Create an alert** — fill in city + filters and save; confirm the alert appears in the list.

Back on the VM:

```bash
# Canary: fetches a real Yad2 page and exits 0 if the parser succeeds
docker compose exec scraper python -m apt.canary

# Admin health page (sign in first with an APT_ADMIN_EMAILS address)
# Browse to https://apt.example.com/#/admin
# Yad2 shows healthy; Facebook shows disabled (expected — real scraping is not yet implemented)
```

---

## 5. Backups

**Crontab** — add this to the `ubuntu` user's crontab (`crontab -e`):

```
17 3 * * * cd /home/ubuntu/APT && set -a && . ./.env && set +a && ./deploy/backup.sh >> backups/backup.log 2>&1
```

`backup.sh` takes a hot SQLite snapshot with `.backup`, gzips it under `backups/`, and — if `APT_BACKUP_BUCKET` is set — uploads it to OCI Object Storage via the `oci` CLI. Local copies older than 14 days are pruned automatically. The `set -a && . ./.env && set +a` in the crontab line matters: the script reads `APT_BACKUP_BUCKET` from the shell environment, and cron does not load `.env` by itself.

**OCI CLI setup** — install and configure the OCI CLI on the VM (`pip install oci-cli`), then set `APT_BACKUP_BUCKET` in `.env` to your bucket name.

**Restore drill** — run this once now, not during an incident:

```bash
# Stop write-capable services first
docker compose stop web scraper bot

# Restore (file path is relative to the APT directory)
./deploy/restore.sh backups/<file>.db.gz

# Bring services back up
docker compose start web scraper
# Add bot if it was running:
# docker compose --profile bot start bot
```

`restore.sh` gunzips the backup, atomically replaces the live database, and removes the WAL/SHM sidecar files so SQLite starts clean.

---

## 6. Updating

```bash
git pull
docker compose up -d --build
```

Compose rebuilds only what changed, re-runs `migrate` (idempotent), and hot-swaps the containers.

---

## 7. Operational Notes

**Rotating `APT_SECRET_KEY`** — changing this value invalidates all session cookies; every user will be logged out on their next request.

**Rate limiter and forwarded IPs** — the `web` service has `APT_BEHIND_PROXY=1` hard-coded in `docker-compose.yml`. This tells the rate limiter to trust the `X-Forwarded-For` header that Caddy injects, so limits are applied per real client IP rather than per Caddy container IP.

**Pruning `search_log`** — the `search_log` table grows with every public search. Prune rows older than 90 days periodically:

```bash
docker compose exec web python -c "from apt.api.config import load_web_config; from apt.repo.db import connect; c = connect(load_web_config().db_path); c.execute(\"DELETE FROM search_log WHERE searched_at < datetime('now', '-90 days')\"); c.commit(); print('pruned')"
```

**Scraping-block runbook** — if the canary starts failing:

1. `docker compose exec scraper python -m apt.canary` — confirm the failure.
2. Check the admin health page for the Yad2 source status.
3. Consider raising `APT_SCRAPE_INTERVAL_SECONDS` (default 900 s) in `.env` and restarting the scraper, or temporarily pausing the source from the admin UI.

---

## 8. Known Deferred Items

The following features are scoped for future work and are **not** present in the current release:

- **Real Facebook scraping** — requires session provisioning and a parser for Facebook Marketplace listings. The source skeleton and admin health entry exist but the scraper is disabled.
- **WhatsApp channel** — alert delivery via WhatsApp is not yet implemented.
- **Session revocation** — there is no UI or API to invalidate individual user sessions. Rotating `APT_SECRET_KEY` is the blunt-force alternative.
