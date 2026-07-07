# APT Backend

Core library for APT (see `docs/superpowers/specs/` for the full design).
This package currently contains the domain layer and SQLite repositories;
the scraper, bot, and web API services build on it (plans 2-4).

## Layout

- `apt/domain/` — Pydantic models, match events, and the pure `listing_matches` function
- `apt/repo/` — SQLite (WAL) repositories; all persistence goes through here
- `apt/sources/` — listing sources; `yad2_parse` (pure parsing) + `yad2` (HTTP client) + city registry
- `apt/notify/` — notifier protocol; `LogNotifier` placeholder until plan 3's channels
- `apt/cycle.py` — the scrape-and-match cycle
- `apt/scraper_main.py` — scraper service entrypoint

## Development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Conventions

- Repositories never read the clock: pass `now` (UTC `datetime`) explicitly.
- Timestamps are ISO-8601 UTC strings in the DB.
- Sources: `yad2`, `facebook`. Channels: `telegram`, `email`.
- Schema changes: append a script to `MIGRATIONS` in `apt/repo/db.py`; never edit past entries.

## Running the scraper

```bash
APT_DB_PATH=data/apt.db APT_SCRAPE_INTERVAL_SECONDS=900 python -m apt.scraper_main
```

New Yad2 cities are added in `apt/sources/yad2_locations.py` (`KNOWN_CITIES`).
Yad2 endpoint/JSON contract: `docs/superpowers/specs/2026-07-07-yad2-reference-notes.md`.
