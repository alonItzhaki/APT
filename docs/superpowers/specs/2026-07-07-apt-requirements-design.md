# APT — Apartment Rental Search Service: Requirements & Design

**Date:** 2026-07-07
**Status:** Approved design, pre-implementation
**Predecessor:** [APT-APT](https://github.com/RachelBernad/APT-APT) — a single-user Yad2 scraper + Telegram bot with hardcoded filters, JSON-file storage, and Docker-on-Raspberry-Pi deployment.

## 1. Purpose

APT is a free hosted web service + Telegram bot that helps apartment hunters in Israel find rentals fast. It continuously collects listings from Yad2 and Facebook, lets anyone search them in a friendly Hebrew web UI, and pushes instant alerts when new listings match a user's saved search. In the Israeli rental market, responding within minutes of a listing appearing is the difference between getting a viewing and missing out — speed of notification is the core value.

### What changes vs. APT-APT

| | APT-APT (old) | APT (new) |
|---|---|---|
| Users | One person, filters hardcoded in Python config | Any number of users, each with their own saved searches |
| Interface | Telegram bot only | Web UI (search + alert management) **and** Telegram bot |
| Audience | The developer | Non-technical people — nothing to install or configure |
| Storage | JSON files | SQLite database (WAL mode) |
| Coverage | Krayot/Haifa, hardcoded | Any city/neighborhood in Israel, chosen per user |
| Deployment | Docker on a home Raspberry Pi | Docker Compose on an Oracle Cloud Always-Free VM |

## 2. Users & Product Model

- **Product model:** one hosted instance, operated by Alon. Users access it via a public HTTPS website and a public Telegram bot. Nobody installs anything.
- **Target users:** non-technical apartment hunters in Israel. A user who can use Facebook can use APT.
- **Operator/admin:** Alon (sole operator).
- **Language:** Hebrew, right-to-left UI, mobile-first. (Listings arrive in Hebrew from the sources.)

## 3. Functional Requirements

### 3.1 Search (no sign-in required)

- Anyone can open the site and search all collected listings.
- Filters: city/neighborhood, price range, rooms range, size (sqm), floor range, mamad (safe room), elevator, entry date.
- Results are listing cards: photo, price, location, rooms/size/floor, amenity badges, description snippet, link to the original listing at the source, first-seen time.
- Default sort: newest first. Price sort also available.

### 3.2 Accounts

- Sign-in: **Google OAuth** only (no passwords to manage). Session held in a secure cookie.
- After sign-in, a user can **link a Telegram account** once, via a deep-link from the site to the bot (`https://t.me/<bot>?start=<link-token>`).
- Users can delete their account and all their data from the UI.

### 3.3 Saved alerts

- A signed-in user saves any search as a named alert (e.g., "3 חדרים בגבעתיים עד 6,000₪").
- Multiple alerts per user. Each can be edited, paused/resumed, or deleted.
- Per alert, the user picks notification channels: Telegram, email, or both.

### 3.4 Notifications

- Fired when a **new listing matches** an active alert, or when a **matched listing's price drops**.
- Channels in v1: **Telegram** (primary) and **email**. The email provider is chosen during implementation; it must have a free tier of at least 100 emails/day (candidates: Brevo, Resend). **WhatsApp is a future phase** — its Business API is paid and requires approval.
- Delivery guarantees: a `sent_notifications` record ensures no user is ever notified twice for the same alert × listing, including across restarts.
- Per-user rate limiting and Telegram flood-control handling (retry with backoff, auto-unsubscribe chats that blocked the bot).

### 3.5 Telegram bot

- Remains fully usable without the website for basic flows: see latest matches for your alerts, pause/resume alerts, help.
- Creating and editing alert filters happens on the website (richer forms); the bot links there.
- Runs in polling mode (no webhook infrastructure needed).

### 3.6 Listing sources

- **Yad2** (primary): generalized from the hardcoded Krayot config to any Israeli city/neighborhood. Scrapes via Yad2's Next.js data endpoints as in the predecessor.
- **Coverage model:** the scraper does not crawl all of Israel blindly. It scrapes the union of locations referenced by active alerts and recent searches. When a user searches a location not yet covered, that location is added to the scrape set and picked up on the next cycle; the UI shows "collecting listings for this area — check back in ~15 minutes" instead of an empty result. Locations unused for 30 days drop out of the scrape set.
- **Facebook** (secondary, best-effort): Marketplace/groups scraping **requires an authenticated session** — a dedicated Facebook account whose login cookies the scraper uses. Sessions expire and automated accounts risk checkpoints/bans, so:
  - Facebook is behind an admin toggle and is never load-bearing: the product is fully functional on Yad2 alone.
  - A dead Facebook session surfaces in admin health, never breaks the site, bot, or Yad2 flow.
- All sources normalize into one listing model and are deduplicated across sources where identity can be established.

### 3.7 Admin

- Admin-only view showing: per-source health (last run, last success, last error), user/alert/listing counts, and per-source enable/disable toggles.

### 3.8 Out of scope for v1

Posting listings, contacting landlords through the platform, roommate matching, payments, mobile apps, WhatsApp notifications, bilingual UI.

## 4. Architecture

### 4.1 Stack

- **Backend:** Python 3.12, FastAPI (async), one codebase — reusing/adapting the proven Yad2 scraper and Telegram bot logic from APT-APT.
- **Frontend:** React + Vite + TypeScript, managed with **pnpm**. Hebrew RTL, mobile-first. Built to static files served by the backend.
- **Database:** SQLite in WAL mode, one file.
- **Hosting:** Oracle Cloud Always-Free ARM VM (Ubuntu), chosen for ₪0 cost with datacenter reliability (no always-on machine available at home).
- **Ops:** Docker Compose; HTTPS via Caddy (automatic free TLS certificates).

### 4.2 Services (Docker Compose)

| Service | Responsibility |
|---|---|
| `web` | FastAPI: REST API + serves the built React app |
| `scraper` | Every ~15 min: fetch Yad2 (+ Facebook if healthy), normalize, dedupe, detect price changes, write listings, then run alert matching and enqueue notifications |
| `bot` | Telegram bot (polling): account linking, latest matches, pause/resume |
| `caddy` | HTTPS termination / reverse proxy |

All services share the SQLite file on a mounted volume. Each restarts independently on crash (`restart: unless-stopped`).

**Why Docker Compose (revisiting the original "no Docker" instinct):** the objection to Docker in APT-APT was that *end users* had to build and run containers. In the hosted model, users only visit a website — Docker is purely the operator's tool. Compose makes the whole system one declarative file, so if the Oracle VM is ever lost (see risk 4), rebuilding on any host is `git clone` + `docker compose up` + restore backup — minutes, not an evening.

### 4.3 Data model (core tables)

- `users` — Google identity (sub), email, linked Telegram chat ID, created/last-seen timestamps
- `alerts` — user ID, name, filters (locations, price range, rooms range, min size, floor range, mamad, elevator, entry date), channels, active flag
- `listings` — source (`yad2`/`facebook`), source ID, canonical ID, price, city/neighborhood/street, rooms, size, floor, mamad, elevator, tags, description, listing URL, photo URLs, first-seen / last-seen timestamps
- `price_history` — listing ID, price, observed-at
- `sent_notifications` — alert ID × listing ID × channel, sent-at (uniqueness constraint = the no-double-send guarantee)
- `source_state` — per source: enabled flag, last run, last success, last error, session metadata (Facebook)

Data access goes through a repository layer so a future SQLite → PostgreSQL migration is a contained change, not a rewrite.

### 4.4 Concurrency ("parallel usage")

- FastAPI async + multiple uvicorn workers: many simultaneous browsing/searching users.
- SQLite WAL mode: unlimited parallel readers alongside the (single) writer. Write load is inherently tiny — one scraper burst per cycle plus occasional alert edits — so contention is negligible at target scale.
- Scraper fetches pages/sources concurrently (asyncio) but rate-limits per site with randomized delays.

### 4.5 Backups

Nightly cron copies the SQLite file (and Facebook session state) off-VM to Oracle Object Storage (included in the free tier). Restore procedure is documented and tested once before launch.

## 5. Non-Functional Requirements

- **Cost:** ₪0/month (Oracle free tier, free email tier, free Google OAuth, free Telegram). Optional: custom domain ~$10/year; a free subdomain is acceptable.
- **Freshness:** new Yad2 listing → matching subscribers notified within ~20 minutes (15-min cycle + processing).
- **Scale target:** tens of simultaneous web users; hundreds of registered users; thousands of active listings — without degradation.
- **Reliability:** auto-restart on crash; a failing source never takes down the site or bot; nightly off-VM backups.
- **Usability:** Hebrew RTL, mobile-first, zero technical knowledge assumed.
- **Privacy:** store the minimum (Google ID, email, Telegram chat ID, alerts); no ad tracking; self-service account deletion.

## 6. Risks

1. **Scraping blocks (existential):** Yad2 may block datacenter IPs or change its internal endpoints. Mitigations: polite randomized rate limits, realistic browser headers, scraping only watched locations, per-source health monitoring for fast detection. If blocking becomes chronic, fallback options include routing scraper traffic through a residential connection.
2. **Facebook fragility:** authenticated-session scraping breaks often (expired sessions, checkpoints, bans). Treated as best-effort and admin-toggleable; never load-bearing.
3. **Terms of service:** scraping likely violates Yad2's and Facebook's ToS. Accepted for a free personal/community tool; any commercial turn would require licensed data sources.
4. **Oracle account reclaim:** rare reclamation of idle always-free accounts. Mitigated by Docker Compose portability + off-VM backups (rebuild anywhere in minutes); keeping the account active.

## 7. Roadmap (post-v1)

WhatsApp notifications → map view → favorites & notes → price-history charts → more sources (Homeless, Madlan, Komo) → bilingual UI (Hebrew/English).

## 8. Success Criteria for v1

- A non-technical user can, unaided: open the site on a phone, search listings, sign in with Google, save an alert, link Telegram, and receive a notification for a new matching listing.
- The operator can rebuild the entire service on a fresh VM from the repo + latest backup in under 30 minutes.
- The system runs a full week unattended with Yad2 healthy and no duplicate notifications.
