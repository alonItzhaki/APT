# APT Backend

Core library for APT (see `docs/superpowers/specs/` for the full design).
This package currently contains the domain layer and SQLite repositories;
the scraper, bot, and web API services build on it (plans 2-4).

## Layout

- `apt/domain/` — Pydantic models and the pure `listing_matches` function
- `apt/repo/` — SQLite (WAL) repositories; all persistence goes through here

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
