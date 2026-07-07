# APT — Full Design Document

**Date:** 2026-07-07
**Status:** Approved design, pre-implementation
**Companion:** [Requirements & Design](2026-07-07-apt-requirements-design.md) — the *what*. This document is the *how* and, most importantly, the *why* behind every architecture, infrastructure, and technology selection.

## 1. System Overview

```
                                    ┌─────────────────────────────────────────────┐
                                    │        Oracle Cloud Always-Free VM          │
                                    │            (Docker Compose)                 │
  Users (phone/desktop)             │                                             │
  ┌──────────┐   HTTPS              │  ┌───────┐      ┌──────────────────────┐    │
  │ Browser  │──────────────────────┼─▶│ caddy │─────▶│ web (FastAPI + SPA)  │    │
  └──────────┘                      │  └───────┘      └──────────┬───────────┘    │
                                    │                            │                │
  ┌──────────┐   Telegram API       │  ┌──────────────┐          ▼                │
  │ Telegram │◀─────────────────────┼──│ bot (polling)│───▶ ┌─────────┐           │
  └──────────┘                      │  └──────────────┘     │ SQLite  │           │
                                    │                       │  (WAL)  │           │
  ┌──────────┐                      │  ┌──────────────┐     └─────────┘           │
  │  Email   │◀─────────────────────┼──│   scraper    │──────────┘                │
  └──────────┘   SMTP/API           │  │ (15-min loop)│                           │
                                    │  └──────┬───────┘                           │
                                    └─────────┼───────────────────────────────────┘
                                              │ HTTPS (outbound only)
                                    ┌─────────▼─────────┐   ┌──────────────────┐
                                    │   Yad2 (primary)  │   │ Facebook (best-  │
                                    │                   │   │ effort, session) │
                                    └───────────────────┘   └──────────────────┘

                       Nightly: SQLite file → Oracle Object Storage (backup)
```

One VM, four containers, one database file, outbound-only scraping, two push channels. Every box above is explained and justified below.

## 2. Decision Records

Each decision follows the same format: **context → options considered → decision → why → trade-offs accepted**. These were all discussed and approved during the design conversation; this section is the durable record.

### D1. Product model: single hosted service

- **Context:** the predecessor (APT-APT) required editing Python config files and running Docker yourself. The new project's core goal is "usable by non-engineers."
- **Options:** (a) hosted service; (b) personal instance for a known group; (c) self-hostable product with an easy installer.
- **Decision:** **(a) hosted service** — one instance operated by Alon; users just open a website or a Telegram bot.
- **Why:** "usable by non-engineers" is only truly satisfied when there is *nothing to install*. Any self-hosting story, however polished, excludes the target audience. A hosted service also means one environment to debug instead of N unknown machines.
- **Trade-offs:** Alon becomes responsible for uptime, data, and abuse; the service must be multi-tenant (accounts, per-user data isolation) from day one.

### D2. Hosting: Oracle Cloud Always-Free ARM VM

- **Context:** hard requirement of ₪0/month. No always-on machine exists at home (no Raspberry Pi), which eliminated the "home server + Cloudflare Tunnel" route. Most PaaS free tiers (Railway, Render always-on workers, Fly.io) have been discontinued or are too limited for three always-on processes.
- **Options:**
  1. *Managed PaaS* (~$5–20/mo) — best ops story, fails the free requirement.
  2. *Home hardware + Cloudflare Tunnel* — free and best scraping IP, but no hardware available.
  3. *Serverless split* (Vercel + Supabase + GitHub Actions cron) — free, but three platforms to wire, a webhook rewrite of the bot, imprecise cron, and the worst scraping IP reputation (shared CI ranges).
  4. *Oracle Cloud Always-Free VM* — genuinely free forever (not a trial): 4 ARM cores, 24 GB RAM, 200 GB storage, plus free object storage.
- **Decision:** **Oracle Always-Free VM.**
- **Why:** it is the only option that is simultaneously free, always-on, and lets us keep the simple "one machine, one database file, three processes" architecture. The hardware allotment is absurdly generous for this workload — comparable to a $20+/mo paid tier elsewhere.
- **Trade-offs:** we administer a Linux server (mitigated by D3); Oracle signup is famously finicky; rare reclaims of idle free accounts have happened (mitigated by D3 portability + D12 off-VM backups); a datacenter IP is more likely to be rate-limited by Yad2 than a residential one (mitigated by D11; residential fallback documented in the risks).

### D3. Process management: Docker Compose (not bare systemd)

- **Context:** the user's initial instinct was "Docker is not the best way," rooted in APT-APT where *end users* had to build and run containers. In the hosted model that objection no longer applies — only the operator touches the server.
- **Options:** (a) bare processes under systemd, provisioned by a setup script; (b) Docker Compose.
- **Decision:** **Docker Compose**, with one compose file defining `web`, `scraper`, `bot`, and `caddy`.
- **Why:** the single strongest argument is **portability as insurance**: the Oracle VM is the one component we don't fully control. With Compose, recreating the entire system on any Linux host is `git clone` + restore backup + `docker compose up -d` — minutes instead of an evening of script archaeology. Secondary benefits: identical dev/prod environments, per-service restart policies, and pinned dependencies per image.
- **Trade-offs:** one more layer to learn and debug; slightly higher memory footprint (irrelevant with 24 GB); images must be built for ARM (`linux/arm64` — all chosen technologies support it).

### D4. Reverse proxy & TLS: Caddy

- **Context:** a public website needs HTTPS; certificates must renew themselves on a zero-maintenance budget.
- **Options:** (a) nginx + certbot; (b) Traefik; (c) Caddy.
- **Decision:** **Caddy.**
- **Why:** automatic Let's Encrypt issuance and renewal with a config file that is ~5 lines. nginx+certbot does the same job with two tools, cron jobs, and much more config surface; Traefik's strengths (dynamic container discovery) are wasted on a static four-service topology.
- **Trade-offs:** less community mindshare than nginx; if we ever need exotic proxy behavior we may hit edges — acceptable at this scale.

### D5. Database: SQLite in WAL mode, behind a repository layer

- **Context:** APT-APT used JSON files, which cannot survive multi-user, multi-process reality: the web app, bot, and scraper all read/write concurrently ("parallel usage" is an explicit requirement). The question "do we even need a DB?" was raised — the answer is yes, because we must durably store per-user accounts, alerts, listing history, and exactly-once notification state, with concurrent-write safety and querying.
- **Options:** (a) keep JSON files; (b) SQLite; (c) PostgreSQL in a container; (d) free managed Postgres (Supabase/Neon).
- **Decision:** **SQLite, WAL mode, one file**, accessed only through a repository (data-access) layer.
- **Why:**
  - *vs JSON files:* files have no atomic concurrent writes, no queries, no constraints — the double-notification and lost-update bugs would be inherent.
  - *vs Postgres-in-container:* Postgres adds a server process, credentials, tuning, and migration/backup machinery for zero benefit at hundreds-of-users scale. SQLite in WAL mode allows unlimited concurrent readers alongside a writer; our write load (one scraper burst / 15 min + occasional alert edits) is trivially inside its comfort zone. Backup = copy one file.
  - *vs managed Postgres:* introduces an external dependency, network latency, and free-tier suspension rules (e.g., Supabase pauses after 7 idle days) for a database that comfortably fits in a file.
- **Trade-offs:** single-writer ceiling — if APT ever reaches thousands of active users with heavy write traffic, we migrate to PostgreSQL. The repository layer exists precisely so that migration is a contained change, not a rewrite.

### D6. Backend: Python 3.12 + FastAPI

- **Context:** the highest-value existing asset is the proven Yad2 scraper and Telegram bot logic — both Python, both async (aiohttp / python-telegram-bot).
- **Options:** (a) FastAPI; (b) Flask; (c) Django; (d) Node/TypeScript backend.
- **Decision:** **FastAPI**, one Python codebase shared by all three services.
- **Why:** rewriting working scraper/bot code in another language is pure risk with no user-visible payoff, so Python wins by inheritance. Within Python: the scrapers and bot are already asyncio-based, and FastAPI is async-native (Flask is not, and its async story is bolted on); Pydantic gives request/response validation of filter payloads nearly for free; automatic OpenAPI docs help when wiring the React frontend. Django brings an ORM/admin/auth stack tuned for server-rendered monoliths — heavier than needed for an API + SPA design.
- **Trade-offs:** FastAPI is less "batteries included" than Django — we assemble auth (D9) and migrations ourselves; that assembly is small and standard.

### D7. Frontend: React + Vite + TypeScript SPA (pnpm), served as static files

- **Context:** the UI must feel like an app to non-technical, mobile-first, Hebrew-speaking users: instant filtering, listing cards, saved-alert management.
- **Options (approaches A/B/C from the design conversation):**
  - *A. FastAPI + React SPA* — modern UX, two ecosystems.
  - *B. Server-rendered Jinja2 + HTMX* — one language, fastest v1, plainer UX with a lower ceiling (map view, instant filters get harder later).
  - *C. Next.js owns UI+API, Python demoted to scraper service* — best UI foundation, but forces rewriting accounts/bot orchestration in TypeScript and doubles the operational stack.
- **Decision:** **A — React + Vite + TypeScript**, built to static files and served by FastAPI (no Node server in production).
- **Why:** the roadmap (map view, price charts, favorites) needs a real client-side foundation; B would hit its ceiling exactly there. C pays a rewrite tax now for benefits we don't need yet. Serving the built SPA from FastAPI keeps production to a single web container. Vite is the current default build tool (fast, minimal config); TypeScript catches filter-shape mismatches against the Pydantic API models; **pnpm** per user's standard for all frontend projects.
- **Trade-offs:** two ecosystems (Python + TS) and a build step; SEO is weak for an SPA — acceptable because listings are intentionally not a public SEO play (scraped content), and users arrive by link/word of mouth.

### D8. UI language: Hebrew, RTL, mobile-first

- **Options:** Hebrew only; Hebrew+English (i18n from day one); English only.
- **Decision:** **Hebrew only** for v1; bilingual is on the roadmap.
- **Why:** the audience is Israeli apartment hunters and the listing content itself is Hebrew. i18n infrastructure from day one roughly doubles UI text work for an audience that isn't there yet. RTL is designed in from the start (retrofitting RTL is far more painful than starting with it). Mobile-first because apartment hunting happens on phones, from bus stops, fast.
- **Trade-offs:** excludes non-Hebrew speakers until the roadmap item lands.

### D9. Authentication: Google OAuth + optional Telegram link

- **Options:** (a) Google OAuth with Telegram linking; (b) Telegram Login Widget as the sole identity; (c) email+password; (d) anonymous browsing with accounts only for alerts.
- **Decision:** **(a) + (d) combined:** browsing/search requires no account; saving alerts requires Google sign-in; Telegram is linked once via bot deep-link (`t.me/<bot>?start=<one-time-token>`) for those who want bot notifications.
- **Why:** Google covers virtually every Israeli smartphone user with zero password management on our side (no reset flows, no breach liability). Telegram-only identity would exclude non-Telegram users from the *website*, inverting the accessibility goal. Email+password is maximal friction and maximal security surface for the least benefit. Free browsing lets people feel the value before any commitment — important for non-technical adopters.
- **Trade-offs:** dependency on Google OAuth availability/policies; users without Google accounts (rare) are excluded from alerts in v1. Session = signed secure cookie; no JWT infrastructure needed for a same-origin SPA.

### D10. Telegram bot: polling mode

- **Options:** long-polling vs webhooks.
- **Decision:** **polling**, as in the predecessor.
- **Why:** polling needs no public endpoint, no webhook TLS wiring, no request-signature handling, and it's the mode the inherited bot code already uses. On an always-on VM, webhooks' only real advantage (no idle connection) is worthless.
- **Trade-offs:** marginally higher idle resource use — irrelevant here. (Webhooks would become necessary only on serverless hosting, which we rejected in D2.)

### D11. Scraping architecture: coverage-driven, rate-limited, source-isolated

- **Context:** scraping is both the product's engine and its biggest existential risk (blocks, endpoint changes, ToS).
- **Decisions & why:**
  - **Yad2 primary via Next.js data endpoints** — the technique proven in APT-APT (fetch `build_id`, page the JSON feed per location). Structured JSON, no HTML brittleness.
  - **Coverage-driven scraping:** scrape only the union of locations referenced by active alerts and recent searches, not all of Israel. Why: a national crawl every 15 minutes is exactly the traffic pattern that gets an IP banned, and 99% of it would serve nobody. A location searched for the first time enters the scrape set on the next cycle (UI communicates the ~15-minute wait); locations unused for 30 days drop out.
  - **Facebook secondary, session-based, admin-toggleable:** requires cookies of a dedicated logged-in account (user-confirmed requirement). Sessions expire and automated accounts get checkpointed, so Facebook must never be load-bearing: it's behind an admin toggle, its failures surface in admin health, and the product is fully functional on Yad2 alone.
  - **Source isolation:** each source implements a common `Source` interface (fetch → normalize → list of canonical listings). One source throwing cannot abort the cycle for others — same registry pattern as the predecessor's `SCRAPER_REGISTRY`, formalized.
  - **Politeness:** randomized inter-request delays (2–8 s), realistic browser headers, concurrent-but-capped fetching per source (asyncio semaphore). Not stealth — politeness, to stay under abuse thresholds.
- **Trade-offs:** a new area shows no results for up to one cycle; Facebook coverage will be intermittent by design.

### D12. Notifications: Telegram + email in v1, exactly-once by construction

- **Options per channel:** Telegram (free, instant, proven), email (free tier, universal), WhatsApp (dominant in Israel but paid Business API + approval process), web-push (unreliable on iOS Safari).
- **Decision:** **Telegram + email** in v1; **WhatsApp deferred** to the roadmap; delivery deduplicated via a `sent_notifications` uniqueness constraint (alert × listing × channel).
- **Why:** Telegram is the predecessor's proven channel and costs nothing. Email covers users without Telegram using the address Google sign-in already provides; provider must offer ≥100 emails/day free (candidates: Brevo, Resend — final pick at implementation). WhatsApp's cost and approval pipeline make it a poor v1 bet despite its popularity. Exactly-once delivery is enforced by the database, not by process memory, so restarts can never re-spam users — a direct lesson from the predecessor's file-based state.
- **Trade-offs:** email deliverability requires domain auth (SPF/DKIM) care; WhatsApp users wait for phase 2. Telegram flood control is handled with parse-retry-backoff and auto-removal of chats that blocked the bot (logic inherited from APT-APT).

### D13. Backups: nightly SQLite snapshot to Oracle Object Storage

- **Options:** no backups; snapshot to a second disk on the same VM; off-VM object storage.
- **Decision:** **nightly off-VM backup** (SQLite `.backup` snapshot + Facebook session state, uploaded to Oracle Object Storage, which is in the free tier), with a documented, once-tested restore procedure.
- **Why:** same-VM backups die with the VM — and the VM (Oracle reclaim, D2) is precisely the component we're insuring against. The entire recovery story is: fresh host + `docker compose up` + restore last night's file.
- **Trade-offs:** up to 24 h of data loss in the worst case — acceptable: listings re-scrape themselves; only alerts/accounts created in the gap are lost.

## 3. Component Design

One repository, two top-level projects:

```
apt/
├── backend/                  # Python (FastAPI, scraper, bot)
│   ├── apt/
│   │   ├── api/              # FastAPI routers: listings, alerts, auth, admin
│   │   ├── domain/           # models: Listing, Alert, User, filter matching
│   │   ├── repo/             # repository layer over SQLite (the D5 seam)
│   │   ├── sources/          # Source interface + yad2.py + facebook.py
│   │   ├── notify/           # channel senders: telegram, email; dedup logic
│   │   ├── scraper_main.py   # entrypoint: 15-min cycle loop
│   │   ├── bot_main.py       # entrypoint: telegram polling bot
│   │   └── web_main.py       # entrypoint: uvicorn app
│   └── tests/
├── frontend/                 # React + Vite + TS (pnpm), Hebrew RTL
│   └── src/ (pages: search, alerts, account, admin)
├── deploy/
│   ├── docker-compose.yml    # web, scraper, bot, caddy
│   ├── Caddyfile
│   └── backup.sh             # nightly cron on the VM
└── docs/
```

**Unit boundaries** (each answers: what it does / how it's used / what it depends on):

| Unit | Purpose | Interface | Depends on |
|---|---|---|---|
| `sources/*` | Turn one external site into normalized listings | `Source.fetch(locations, filters) -> list[Listing]` | HTTP only — no DB access |
| `repo/*` | All persistence | Typed methods (`save_listings`, `alerts_matching`, `mark_sent`…) | SQLite only |
| `domain/matching` | Does listing X satisfy alert Y | Pure function — no I/O | nothing |
| `notify/*` | Deliver one notification on one channel | `Channel.send(user, listing, alert)` | repo (dedup), external APIs |
| `api/*` | HTTP surface for the SPA | REST + OpenAPI | repo, domain |
| Scraper loop | Orchestrates cycle: sources → repo → matching → notify | cron-like process | all of the above |

The matching logic being a pure function is deliberate: it is the correctness-critical core (wrong matches = spam or silence), and pure functions are the easiest thing in the system to test exhaustively.

## 4. Key Data Flows

### 4.1 Scrape-and-notify cycle (every ~15 min, `scraper` service)

1. Load the active **scrape set**: locations from active alerts ∪ recent searches (≤30 days).
2. For each enabled source, fetch listings for those locations (concurrent, rate-limited). A source failure is logged to `source_state` and skipped.
3. Normalize → upsert into `listings`; price differences append to `price_history`.
4. For each new/price-dropped listing, evaluate `domain.matching` against all active alerts.
5. For each match, for each of the alert's channels: attempt `INSERT` into `sent_notifications` (unique constraint); only on success, send. Exactly-once falls out of the constraint.
6. Update `source_state` (last run/success/error) — this is what the admin page reads.

### 4.2 New-user alert setup

Google sign-in → user row created → user builds filters in the search UI → "save as alert" → optional Telegram linking via `t.me/<bot>?start=<token>` (bot resolves token → stores chat ID on the user) → next cycle onward, notifications flow.

### 4.3 Search in an uncovered location

Search executes against existing listings; the location is enqueued into the scrape set; UI shows "collecting listings for this area — check back in ~15 minutes" when results are empty because coverage is new.

## 5. Error Handling & Observability

- **Per-source containment:** a crashing source never aborts the cycle (try/except per source, status recorded).
- **Per-service containment:** `restart: unless-stopped` on every container; the site stays up when the scraper is down and vice versa.
- **Telegram failures:** flood-control retry with parsed wait time + jitter; `Forbidden` (user blocked bot / chat gone) removes the chat ID — inherited, proven behavior.
- **Email failures:** logged and retried next cycle (the `sent_notifications` row is only written on success).
- **Observability (v1-appropriate):** structured logs per service (`docker compose logs`), the admin health page (last success per source, counts), and an external free uptime ping (e.g., UptimeRobot) on `/healthz`. No metrics stack in v1 — the admin page is the dashboard.

## 6. Security Considerations

- HTTPS everywhere (Caddy, HSTS). Secure, HttpOnly, SameSite cookies for sessions.
- OAuth `state` validation; Telegram link tokens are single-use and short-lived.
- Admin routes gated on Alon's Google identity.
- Rate limiting on API endpoints (per-IP) to protect the free VM from abuse.
- Secrets (bot token, OAuth client, email API key, Facebook session) live in an `.env` file on the VM only — never in git. The backup bundle is private-bucket only.
- The VM exposes ports 80/443 exclusively; SSH by key only.

## 7. Testing Strategy

- **Pure core first:** exhaustive unit tests for `domain/matching` (every filter type, boundary values, missing fields) — the highest-value tests in the system.
- **Repository tests** against a temp SQLite file, including the `sent_notifications` uniqueness guarantee and WAL concurrent read/write smoke test.
- **Source tests** with recorded JSON fixtures from Yad2 (no live HTTP in CI); normalization edge cases (missing price, weird floors).
- **API tests** via FastAPI's test client: auth flows, alert CRUD, admin gating.
- **Frontend:** component tests for the filter form and listing card; one Playwright happy-path (search → sign in → save alert) if time permits.
- **Live-scrape canary:** a manual/CI-scheduled job that runs one real Yad2 fetch and alerts if the endpoint contract changed — because the real failure mode is *them changing*, not our regressions.

## 8. Decisions Deliberately Deferred to Implementation

- Email provider final pick (Brevo vs Resend — criteria fixed in D12).
- SQLite migration tooling (hand-rolled versioned SQL vs Alembic).
- Exact React component library (must support RTL well; e.g., MUI with RTL cache) — chosen during frontend setup.
- Oracle subdomain vs purchased domain (~$10/yr, the only optional cost).
