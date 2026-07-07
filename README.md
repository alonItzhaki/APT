# APT — חיפוש דירות להשכרה

Apartment-rental search service for Israel: a Hebrew (RTL) web UI + Telegram bot
that continuously collects listings from Yad2 and alerts users within minutes
when new listings match their saved searches. In the Israeli rental market,
responding fast is the whole game — speed of notification is the core value.

## Features

- **Search without signing in** — filter by city/neighborhood, price, rooms, size, floor, ממ"ד, elevator.
- **Saved alerts** — sign in with Google, save any search as a named alert, get notified on new listings and price drops.
- **Notification channels** — Telegram (link your account once via the bot) and email (Brevo); exactly-once delivery guaranteed at the database level.
- **Telegram bot** — `/matches`, `/pause`, `/resume` without opening the site.
- **Admin panel** — scraper health per source, user/alert/listing counts, per-source enable/disable.
- **Coverage-driven scraping** — only locations that users actually watch are scraped; searching a new area adds it to the next cycle (~15 min).

## Architecture

One Docker Compose stack on a single VM (designed for Oracle Cloud's Always-Free ARM tier — ₪0/month):

| Service | What it does |
|---|---|
| `web` | FastAPI: REST API + serves the built React SPA |
| `scraper` | Every ~15 min: fetch Yad2, store listings, match against alerts, notify |
| `bot` | Telegram bot (polling), under the `bot` compose profile |
| `caddy` | HTTPS termination with automatic Let's Encrypt certificates |
| `migrate` | One-shot: applies SQLite migrations before anything starts |

Storage is a single SQLite file (WAL mode) shared by all services, with nightly
off-VM backups. Full design rationale — every architecture, infra, and
technology decision with alternatives and trade-offs — lives in
[`docs/superpowers/specs/`](docs/superpowers/specs/).

**Tech stack:** Python 3.12 · FastAPI · aiohttp · python-telegram-bot · SQLite (WAL) · React 18 · TypeScript · Vite · pnpm · Docker Compose · Caddy.

## Repository layout

```
backend/    Python package `apt` — domain, repos, sources, notify, bot, API (see backend/README.md)
frontend/   React SPA, Hebrew RTL (see frontend/README.md)
deploy/     Caddyfile, backup/restore scripts
docs/       Requirements, full design doc, implementation plans
DEPLOY.md   Production runbook (Oracle VM, step by step)
```

## Development

Backend (Python 3.12, tests included):

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate   # or: uv venv --python 3.12 .venv
pip install -e '.[dev]'
pytest                                                   # 183 tests
python -m apt.web_main                                   # API on :8000
```

Frontend (Node 20 + pnpm):

```bash
cd frontend
pnpm install
pnpm test          # 22 tests
pnpm dev           # dev server, proxies /api to :8000
```

## Deployment

See **[DEPLOY.md](DEPLOY.md)** — from a bare Oracle Always-Free VM to a running
production instance: Docker, `.env` setup, Google OAuth, verification checklist,
backups, and the restore drill.

## Status & roadmap

v1 is code-complete (205 tests across backend + frontend). Deferred to future
releases: real Facebook Marketplace scraping (a disabled, session-gated skeleton
ships today), WhatsApp notifications, map view, price-history charts, favorites,
and a bilingual UI. Details in `docs/superpowers/specs/` and `DEPLOY.md` §8.
