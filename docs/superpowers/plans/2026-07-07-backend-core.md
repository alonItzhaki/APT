# APT Plan 1/6: Backend Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the tested foundation of the APT backend: domain models, the pure alert-matching function, and the SQLite (WAL) repository layer — everything later plans (scraper, bot, API) will build on.

**Architecture:** One Python package `apt` under `backend/`. Pydantic v2 domain models; a pure `listing_matches` function (no I/O) as the correctness-critical core; a repository layer over stdlib `sqlite3` with WAL mode and versioned migrations. No web server, no scraping, no Telegram in this plan — those are plans 2–4 and consume the interfaces defined here.

**Tech Stack:** Python 3.12, Pydantic ≥2.7, stdlib sqlite3, pytest.

**Specs:** `docs/superpowers/specs/2026-07-07-apt-requirements-design.md`, `docs/superpowers/specs/2026-07-07-apt-full-design.md` (decision records D5, D6; component design §3; data model §4.3 of requirements).

## Global Constraints

- Python `>=3.12`; dependencies for this plan: `pydantic>=2.7` (runtime), `pytest>=8` (dev). No SQLAlchemy, no ORM — repositories use stdlib `sqlite3` (design D5).
- Every SQLite connection sets `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON`.
- Repositories never read the clock — `now: datetime` (UTC) is always a parameter. Timestamps stored as ISO-8601 UTC strings.
- Exactly-once notification state is enforced by a DB uniqueness constraint, not application logic.
- Sources are `"yad2"` and `"facebook"`; channels are `"telegram"` and `"email"` — exact strings everywhere.
- All work happens in `/Users/alon.i/APT`. Run all backend commands from `backend/` with the venv activated (`source .venv/bin/activate`).
- Comments only for non-obvious business rules; never narrate what code does.

---

### Task 1: Backend project scaffold

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/apt/__init__.py`
- Create: `backend/apt/domain/__init__.py`
- Create: `backend/apt/repo/__init__.py`
- Create: `backend/tests/__init__.py`
- Test: `backend/tests/test_sanity.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: an installable package `apt` with subpackages `apt.domain`, `apt.repo`; `pytest` runs from `backend/`.

- [ ] **Step 1: Create the project files**

`backend/pyproject.toml`:

```toml
[project]
name = "apt-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["apt*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create empty files: `backend/apt/__init__.py`, `backend/apt/domain/__init__.py`, `backend/apt/repo/__init__.py`, `backend/tests/__init__.py`.

- [ ] **Step 2: Write the sanity test**

`backend/tests/test_sanity.py`:

```python
import apt


def test_package_imports():
    assert apt is not None
```

- [ ] **Step 3: Create venv, install, run the test**

```bash
cd /Users/alon.i/APT/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -v
```

Expected: `1 passed`.

- [ ] **Step 4: Add venv to gitignore and commit**

Append to `/Users/alon.i/APT/.gitignore` (file exists, keep the current `.DS_Store` line):

```
.venv/
__pycache__/
*.egg-info/
```

```bash
cd /Users/alon.i/APT
git add .gitignore backend/
git commit -m "feat: scaffold backend package"
```

---

### Task 2: Domain models

**Files:**
- Create: `backend/apt/domain/models.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces (all Pydantic v2 `BaseModel`s in `apt.domain.models`, imported by every later task):
  - `Location(city: str, neighborhood: str | None = None)`
  - `AlertFilters(locations: list[Location] = [], min_price: int | None = None, max_price: int | None = None, min_rooms: float | None = None, max_rooms: float | None = None, min_size_sqm: int | None = None, min_floor: int | None = None, max_floor: int | None = None, require_mamad: bool = False, require_elevator: bool = False, entry_by: date | None = None)`
  - `Listing(source: Literal["yad2","facebook"], source_id: str, url: str, city: str, price: int | None = None, neighborhood: str | None = None, street: str | None = None, rooms: float | None = None, size_sqm: int | None = None, floor: int | None = None, has_mamad: bool | None = None, has_elevator: bool | None = None, entry_date: date | None = None, tags: list[str] = [], description: str = "", photo_urls: list[str] = [])` with computed property `id` = `f"{source}:{source_id}"`
  - `Alert(id: int, user_id: int, name: str, filters: AlertFilters, channels: list[Literal["telegram","email"]], active: bool = True)`
  - `User(id: int, google_sub: str, email: str, telegram_chat_id: int | None = None)`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_models.py`:

```python
from datetime import date

import pytest
from pydantic import ValidationError

from apt.domain.models import Alert, AlertFilters, Listing, Location, User


def make_listing(**overrides):
    base = dict(source="yad2", source_id="abc123", url="https://example.com/item/abc123", city="חיפה")
    base.update(overrides)
    return Listing(**base)


def test_listing_id_is_source_and_source_id():
    assert make_listing().id == "yad2:abc123"


def test_listing_rejects_unknown_source():
    with pytest.raises(ValidationError):
        make_listing(source="craigslist")


def test_listing_optional_fields_default_to_none_or_empty():
    listing = make_listing()
    assert listing.price is None
    assert listing.rooms is None
    assert listing.tags == []
    assert listing.photo_urls == []
    assert listing.description == ""


def test_alert_filters_all_optional():
    filters = AlertFilters()
    assert filters.locations == []
    assert filters.require_mamad is False
    assert filters.require_elevator is False


def test_alert_filters_roundtrip_json():
    filters = AlertFilters(
        locations=[Location(city="חיפה", neighborhood="קריית חיים מערבית")],
        max_price=6000,
        min_rooms=3.0,
        entry_by=date(2026, 9, 1),
    )
    restored = AlertFilters.model_validate_json(filters.model_dump_json())
    assert restored == filters


def test_alert_rejects_unknown_channel():
    with pytest.raises(ValidationError):
        Alert(id=1, user_id=1, name="x", filters=AlertFilters(), channels=["whatsapp"])


def test_user_telegram_optional():
    user = User(id=1, google_sub="g-123", email="a@b.com")
    assert user.telegram_chat_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/alon.i/APT/backend && source .venv/bin/activate
pytest tests/test_models.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'apt.domain.models'`.

- [ ] **Step 3: Implement the models**

`backend/apt/domain/models.py`:

```python
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, computed_field

Source = Literal["yad2", "facebook"]
Channel = Literal["telegram", "email"]


class Location(BaseModel):
    city: str
    neighborhood: str | None = None


class AlertFilters(BaseModel):
    locations: list[Location] = Field(default_factory=list)
    min_price: int | None = None
    max_price: int | None = None
    min_rooms: float | None = None
    max_rooms: float | None = None
    min_size_sqm: int | None = None
    min_floor: int | None = None
    max_floor: int | None = None
    require_mamad: bool = False
    require_elevator: bool = False
    entry_by: date | None = None


class Listing(BaseModel):
    source: Source
    source_id: str
    url: str
    city: str
    price: int | None = None
    neighborhood: str | None = None
    street: str | None = None
    rooms: float | None = None
    size_sqm: int | None = None
    floor: int | None = None
    has_mamad: bool | None = None
    has_elevator: bool | None = None
    entry_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    description: str = ""
    photo_urls: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def id(self) -> str:
        return f"{self.source}:{self.source_id}"


class Alert(BaseModel):
    id: int
    user_id: int
    name: str
    filters: AlertFilters
    channels: list[Channel]
    active: bool = True


class User(BaseModel):
    id: int
    google_sub: str
    email: str
    telegram_chat_id: int | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_models.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/domain/models.py backend/tests/test_models.py
git commit -m "feat: add domain models"
```

---

### Task 3: Pure matching function

**Files:**
- Create: `backend/apt/domain/matching.py`
- Test: `backend/tests/test_matching.py`

**Interfaces:**
- Consumes: `Listing`, `AlertFilters`, `Location` from Task 2.
- Produces: `listing_matches(listing: Listing, filters: AlertFilters) -> bool` — pure, no I/O. Used by the scraper cycle (plan 2) and by API-side previews (plan 4).

**Matching semantics (the business rules — copy into the module docstring):**
1. **Locations:** empty `filters.locations` matches any location. Otherwise the listing must match at least one filter location: same `city`; if the filter location also sets `neighborhood`, the listing's `neighborhood` must equal it.
2. **Numeric bounds** (`price`, `rooms`, `size_sqm`, `floor`): if a bound is set and the listing's value is `None`, it does **not** match (never notify on unknown data). Bounds are inclusive.
3. **Amenities:** `require_mamad=True` matches only `has_mamad is True` (None fails). Same for elevator.
4. **Entry date:** if `entry_by` is set, a listing with `entry_date is None` **does** match (missing entry date means "immediate" on Israeli listing sites); otherwise `entry_date <= entry_by`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_matching.py`:

```python
from datetime import date

from apt.domain.matching import listing_matches
from apt.domain.models import AlertFilters, Listing, Location


def make_listing(**overrides):
    base = dict(
        source="yad2",
        source_id="x",
        url="https://example.com/x",
        city="חיפה",
        neighborhood="קריית חיים מערבית",
        price=5500,
        rooms=3.5,
        size_sqm=80,
        floor=2,
        has_mamad=True,
        has_elevator=True,
        entry_date=date(2026, 8, 1),
    )
    base.update(overrides)
    return Listing(**base)


def test_empty_filters_match_everything():
    assert listing_matches(make_listing(), AlertFilters())


def test_city_match_and_mismatch():
    filters = AlertFilters(locations=[Location(city="חיפה")])
    assert listing_matches(make_listing(), filters)
    assert not listing_matches(make_listing(city="תל אביב"), filters)


def test_neighborhood_required_when_set_on_filter():
    filters = AlertFilters(locations=[Location(city="חיפה", neighborhood="הדר")])
    assert not listing_matches(make_listing(), filters)
    assert listing_matches(make_listing(neighborhood="הדר"), filters)


def test_any_of_multiple_locations_matches():
    filters = AlertFilters(locations=[Location(city="תל אביב"), Location(city="חיפה")])
    assert listing_matches(make_listing(), filters)


def test_price_bounds_inclusive():
    filters = AlertFilters(min_price=5500, max_price=5500)
    assert listing_matches(make_listing(), filters)
    assert not listing_matches(make_listing(price=5501), filters)
    assert not listing_matches(make_listing(price=5499), filters)


def test_unknown_price_fails_price_filter_but_passes_without_one():
    assert not listing_matches(make_listing(price=None), AlertFilters(max_price=6000))
    assert listing_matches(make_listing(price=None), AlertFilters())


def test_rooms_bounds():
    assert listing_matches(make_listing(), AlertFilters(min_rooms=3.5, max_rooms=4.0))
    assert not listing_matches(make_listing(rooms=3.0), AlertFilters(min_rooms=3.5))
    assert not listing_matches(make_listing(rooms=None), AlertFilters(min_rooms=3.5))


def test_size_and_floor_bounds():
    assert listing_matches(make_listing(), AlertFilters(min_size_sqm=65))
    assert not listing_matches(make_listing(size_sqm=60), AlertFilters(min_size_sqm=65))
    assert not listing_matches(make_listing(floor=5), AlertFilters(max_floor=4))
    assert not listing_matches(make_listing(floor=None), AlertFilters(min_floor=1))


def test_mamad_requirement():
    assert listing_matches(make_listing(), AlertFilters(require_mamad=True))
    assert not listing_matches(make_listing(has_mamad=False), AlertFilters(require_mamad=True))
    assert not listing_matches(make_listing(has_mamad=None), AlertFilters(require_mamad=True))


def test_elevator_requirement():
    assert not listing_matches(make_listing(has_elevator=None), AlertFilters(require_elevator=True))


def test_entry_by_missing_entry_date_means_immediate():
    filters = AlertFilters(entry_by=date(2026, 9, 1))
    assert listing_matches(make_listing(entry_date=None), filters)
    assert listing_matches(make_listing(), filters)
    assert not listing_matches(make_listing(entry_date=date(2026, 10, 1)), filters)


def test_all_filters_together():
    filters = AlertFilters(
        locations=[Location(city="חיפה", neighborhood="קריית חיים מערבית")],
        min_price=3000,
        max_price=6000,
        min_rooms=3.0,
        max_rooms=4.0,
        min_size_sqm=65,
        min_floor=1,
        max_floor=4,
        require_mamad=True,
        require_elevator=True,
        entry_by=date(2026, 9, 1),
    )
    assert listing_matches(make_listing(), filters)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_matching.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'apt.domain.matching'`.

- [ ] **Step 3: Implement the matching function**

`backend/apt/domain/matching.py`:

```python
"""Pure alert-matching rules.

Semantics:
- Empty filter locations match any location; otherwise the listing must match
  at least one filter location (city equal; neighborhood equal too when the
  filter location sets one).
- Numeric bounds are inclusive; a listing with an unknown (None) value fails
  any bound set on that field — we never notify on unknown data.
- require_mamad / require_elevator match only an explicit True.
- entry_by: a missing listing entry_date means "immediate" and matches.
"""

from apt.domain.models import AlertFilters, Listing


def _matches_location(listing: Listing, filters: AlertFilters) -> bool:
    if not filters.locations:
        return True
    for loc in filters.locations:
        if listing.city != loc.city:
            continue
        if loc.neighborhood is not None and listing.neighborhood != loc.neighborhood:
            continue
        return True
    return False


def _within(value: float | None, low: float | None, high: float | None) -> bool:
    if low is None and high is None:
        return True
    if value is None:
        return False
    if low is not None and value < low:
        return False
    if high is not None and value > high:
        return False
    return True


def listing_matches(listing: Listing, filters: AlertFilters) -> bool:
    if not _matches_location(listing, filters):
        return False
    if not _within(listing.price, filters.min_price, filters.max_price):
        return False
    if not _within(listing.rooms, filters.min_rooms, filters.max_rooms):
        return False
    if not _within(listing.size_sqm, filters.min_size_sqm, None):
        return False
    if not _within(listing.floor, filters.min_floor, filters.max_floor):
        return False
    if filters.require_mamad and listing.has_mamad is not True:
        return False
    if filters.require_elevator and listing.has_elevator is not True:
        return False
    if filters.entry_by is not None and listing.entry_date is not None:
        if listing.entry_date > filters.entry_by:
            return False
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_matching.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/domain/matching.py backend/tests/test_matching.py
git commit -m "feat: add pure alert matching function"
```

---

### Task 4: Database connection and migrations

**Files:**
- Create: `backend/apt/repo/db.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Consumes: nothing.
- Produces (module `apt.repo.db`):
  - `connect(path: str | Path) -> sqlite3.Connection` — WAL mode, foreign keys on, `sqlite3.Row` row factory.
  - `migrate(conn: sqlite3.Connection) -> None` — applies pending versioned migrations using `PRAGMA user_version`.
  - Schema v1 tables: `users`, `alerts`, `listings`, `price_history`, `sent_notifications`, `source_state`, `search_log` (columns below).
  - Shared pytest fixture `conn` (fresh migrated temp DB per test).

- [ ] **Step 1: Write the failing tests**

`backend/tests/conftest.py`:

```python
import pytest

from apt.repo.db import connect, migrate


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    migrate(connection)
    yield connection
    connection.close()
```

`backend/tests/test_db.py`:

```python
from apt.repo.db import connect, migrate

EXPECTED_TABLES = {
    "users",
    "alerts",
    "listings",
    "price_history",
    "sent_notifications",
    "source_state",
    "search_log",
}


def test_wal_mode_enabled(tmp_path):
    connection = connect(tmp_path / "wal.db")
    mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


def test_foreign_keys_enabled(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migrate_creates_all_tables(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {row["name"] for row in rows}
    assert EXPECTED_TABLES <= names


def test_migrate_is_idempotent(tmp_path):
    connection = connect(tmp_path / "idem.db")
    migrate(connection)
    migrate(connection)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_db.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'apt.repo.db'`.

- [ ] **Step 3: Implement connection + migrations**

`backend/apt/repo/db.py`:

```python
import sqlite3
from pathlib import Path

MIGRATIONS: list[str] = [
    # v1: initial schema
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        google_sub TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL,
        telegram_chat_id INTEGER,
        created_at TEXT NOT NULL
    );

    CREATE TABLE alerts (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        filters TEXT NOT NULL,
        channels TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE listings (
        id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        source_id TEXT NOT NULL,
        url TEXT NOT NULL,
        city TEXT NOT NULL,
        neighborhood TEXT,
        street TEXT,
        price INTEGER,
        rooms REAL,
        size_sqm INTEGER,
        floor INTEGER,
        has_mamad INTEGER,
        has_elevator INTEGER,
        entry_date TEXT,
        tags TEXT NOT NULL DEFAULT '[]',
        description TEXT NOT NULL DEFAULT '',
        photo_urls TEXT NOT NULL DEFAULT '[]',
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        UNIQUE (source, source_id)
    );
    CREATE INDEX idx_listings_city ON listings(city);
    CREATE INDEX idx_listings_first_seen ON listings(first_seen);

    CREATE TABLE price_history (
        id INTEGER PRIMARY KEY,
        listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
        price INTEGER NOT NULL,
        observed_at TEXT NOT NULL
    );

    CREATE TABLE sent_notifications (
        alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
        listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
        channel TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        PRIMARY KEY (alert_id, listing_id, channel)
    );

    CREATE TABLE source_state (
        source TEXT PRIMARY KEY,
        enabled INTEGER NOT NULL DEFAULT 1,
        last_run TEXT,
        last_success TEXT,
        last_error TEXT
    );

    CREATE TABLE search_log (
        id INTEGER PRIMARY KEY,
        city TEXT NOT NULL,
        neighborhood TEXT,
        searched_at TEXT NOT NULL
    );
    """,
]


def connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    current = connection.execute("PRAGMA user_version").fetchone()[0]
    for version, script in enumerate(MIGRATIONS[current:], start=current + 1):
        with connection:
            connection.executescript(script)
            connection.execute(f"PRAGMA user_version = {version}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_db.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/repo/db.py backend/tests/conftest.py backend/tests/test_db.py
git commit -m "feat: add sqlite connection and versioned migrations"
```

---

### Task 5: User repository

**Files:**
- Create: `backend/apt/repo/users.py`
- Test: `backend/tests/test_users_repo.py`

**Interfaces:**
- Consumes: `connect`/`migrate` fixture from Task 4; `User` model from Task 2.
- Produces (`apt.repo.users.UserRepo`, constructed as `UserRepo(conn)`):
  - `upsert_google_user(google_sub: str, email: str, now: datetime) -> User` — creates on first sign-in, updates email on later sign-ins.
  - `get(user_id: int) -> User | None`
  - `get_by_google_sub(google_sub: str) -> User | None`
  - `get_by_telegram_chat(chat_id: int) -> User | None`
  - `set_telegram_chat(user_id: int, chat_id: int | None) -> None`
  - `delete(user_id: int) -> None` — cascades to the user's alerts (FK).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_users_repo.py`:

```python
from datetime import datetime, timezone

from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


def test_upsert_creates_user(conn):
    repo = UserRepo(conn)
    user = repo.upsert_google_user("g-1", "a@b.com", NOW)
    assert user.id > 0
    assert user.google_sub == "g-1"
    assert user.email == "a@b.com"
    assert user.telegram_chat_id is None


def test_upsert_same_sub_updates_email_keeps_id(conn):
    repo = UserRepo(conn)
    first = repo.upsert_google_user("g-1", "a@b.com", NOW)
    second = repo.upsert_google_user("g-1", "new@b.com", NOW)
    assert second.id == first.id
    assert second.email == "new@b.com"


def test_get_by_google_sub_and_missing(conn):
    repo = UserRepo(conn)
    created = repo.upsert_google_user("g-1", "a@b.com", NOW)
    assert repo.get_by_google_sub("g-1") == created
    assert repo.get_by_google_sub("nope") is None
    assert repo.get(created.id) == created
    assert repo.get(9999) is None


def test_set_and_lookup_telegram_chat(conn):
    repo = UserRepo(conn)
    user = repo.upsert_google_user("g-1", "a@b.com", NOW)
    repo.set_telegram_chat(user.id, 555)
    assert repo.get(user.id).telegram_chat_id == 555
    assert repo.get_by_telegram_chat(555).id == user.id
    repo.set_telegram_chat(user.id, None)
    assert repo.get_by_telegram_chat(555) is None


def test_delete_removes_user(conn):
    repo = UserRepo(conn)
    user = repo.upsert_google_user("g-1", "a@b.com", NOW)
    repo.delete(user.id)
    assert repo.get(user.id) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_users_repo.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'apt.repo.users'`.

- [ ] **Step 3: Implement the repository**

`backend/apt/repo/users.py`:

```python
import sqlite3
from datetime import datetime

from apt.domain.models import User


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        google_sub=row["google_sub"],
        email=row["email"],
        telegram_chat_id=row["telegram_chat_id"],
    )


class UserRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def upsert_google_user(self, google_sub: str, email: str, now: datetime) -> User:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO users (google_sub, email, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT (google_sub) DO UPDATE SET email = excluded.email
                """,
                (google_sub, email, now.isoformat()),
            )
        return self.get_by_google_sub(google_sub)

    def get(self, user_id: int) -> User | None:
        row = self._conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row else None

    def get_by_google_sub(self, google_sub: str) -> User | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE google_sub = ?", (google_sub,)
        ).fetchone()
        return _row_to_user(row) if row else None

    def get_by_telegram_chat(self, chat_id: int) -> User | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE telegram_chat_id = ?", (chat_id,)
        ).fetchone()
        return _row_to_user(row) if row else None

    def set_telegram_chat(self, user_id: int, chat_id: int | None) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE users SET telegram_chat_id = ? WHERE id = ?", (chat_id, user_id)
            )

    def delete(self, user_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_users_repo.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/repo/users.py backend/tests/test_users_repo.py
git commit -m "feat: add user repository"
```

---

### Task 6: Alert repository

**Files:**
- Create: `backend/apt/repo/alerts.py`
- Test: `backend/tests/test_alerts_repo.py`

**Interfaces:**
- Consumes: Task 4 fixture; `Alert`, `AlertFilters` from Task 2; `UserRepo` from Task 5 (tests only).
- Produces (`apt.repo.alerts.AlertRepo(conn)`):
  - `create(user_id: int, name: str, filters: AlertFilters, channels: list[str], now: datetime) -> Alert`
  - `get(alert_id: int) -> Alert | None`
  - `list_for_user(user_id: int) -> list[Alert]`
  - `list_active() -> list[Alert]` — the scraper cycle's input (plan 2).
  - `update(alert_id: int, name: str, filters: AlertFilters, channels: list[str]) -> Alert | None`
  - `set_active(alert_id: int, active: bool) -> None`
  - `delete(alert_id: int) -> None`
  - Filters/channels persisted as JSON text.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_alerts_repo.py`:

```python
from datetime import datetime, timezone

import pytest

from apt.domain.models import AlertFilters, Location
from apt.repo.alerts import AlertRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def user(conn):
    return UserRepo(conn).upsert_google_user("g-1", "a@b.com", NOW)


def make_filters():
    return AlertFilters(locations=[Location(city="חיפה")], max_price=6000, min_rooms=3.0)


def test_create_and_get_roundtrip(conn, user):
    repo = AlertRepo(conn)
    alert = repo.create(user.id, "3 חדרים בחיפה", make_filters(), ["telegram"], NOW)
    assert alert.id > 0
    assert alert.active is True
    fetched = repo.get(alert.id)
    assert fetched == alert
    assert fetched.filters.max_price == 6000
    assert fetched.filters.locations[0].city == "חיפה"


def test_list_for_user_only_their_alerts(conn, user):
    repo = AlertRepo(conn)
    other = UserRepo(conn).upsert_google_user("g-2", "c@d.com", NOW)
    mine = repo.create(user.id, "mine", make_filters(), ["telegram"], NOW)
    repo.create(other.id, "theirs", make_filters(), ["email"], NOW)
    assert [a.id for a in repo.list_for_user(user.id)] == [mine.id]


def test_list_active_excludes_paused(conn, user):
    repo = AlertRepo(conn)
    active = repo.create(user.id, "on", make_filters(), ["telegram"], NOW)
    paused = repo.create(user.id, "off", make_filters(), ["telegram"], NOW)
    repo.set_active(paused.id, False)
    assert [a.id for a in repo.list_active()] == [active.id]
    assert repo.get(paused.id).active is False


def test_update_changes_fields(conn, user):
    repo = AlertRepo(conn)
    alert = repo.create(user.id, "old", make_filters(), ["telegram"], NOW)
    new_filters = AlertFilters(locations=[Location(city="תל אביב")], max_price=8000)
    updated = repo.update(alert.id, "new", new_filters, ["telegram", "email"], )
    assert updated.name == "new"
    assert updated.filters.max_price == 8000
    assert updated.channels == ["telegram", "email"]
    assert repo.update(9999, "x", new_filters, ["email"]) is None


def test_delete_and_user_cascade(conn, user):
    repo = AlertRepo(conn)
    alert = repo.create(user.id, "x", make_filters(), ["telegram"], NOW)
    repo.delete(alert.id)
    assert repo.get(alert.id) is None
    survivor = repo.create(user.id, "y", make_filters(), ["telegram"], NOW)
    UserRepo(conn).delete(user.id)
    assert repo.get(survivor.id) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_alerts_repo.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'apt.repo.alerts'`.

- [ ] **Step 3: Implement the repository**

`backend/apt/repo/alerts.py`:

```python
import json
import sqlite3
from datetime import datetime

from apt.domain.models import Alert, AlertFilters


def _row_to_alert(row: sqlite3.Row) -> Alert:
    return Alert(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        filters=AlertFilters.model_validate_json(row["filters"]),
        channels=json.loads(row["channels"]),
        active=bool(row["active"]),
    )


class AlertRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(
        self,
        user_id: int,
        name: str,
        filters: AlertFilters,
        channels: list[str],
        now: datetime,
    ) -> Alert:
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO alerts (user_id, name, filters, channels, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, name, filters.model_dump_json(), json.dumps(channels), now.isoformat()),
            )
        return self.get(cursor.lastrowid)

    def get(self, alert_id: int) -> Alert | None:
        row = self._conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        return _row_to_alert(row) if row else None

    def list_for_user(self, user_id: int) -> list[Alert]:
        rows = self._conn.execute(
            "SELECT * FROM alerts WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
        return [_row_to_alert(row) for row in rows]

    def list_active(self) -> list[Alert]:
        rows = self._conn.execute(
            "SELECT * FROM alerts WHERE active = 1 ORDER BY id"
        ).fetchall()
        return [_row_to_alert(row) for row in rows]

    def update(
        self,
        alert_id: int,
        name: str,
        filters: AlertFilters,
        channels: list[str],
    ) -> Alert | None:
        with self._conn:
            self._conn.execute(
                "UPDATE alerts SET name = ?, filters = ?, channels = ? WHERE id = ?",
                (name, filters.model_dump_json(), json.dumps(channels), alert_id),
            )
        return self.get(alert_id)

    def set_active(self, alert_id: int, active: bool) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE alerts SET active = ? WHERE id = ?", (int(active), alert_id)
            )

    def delete(self, alert_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_alerts_repo.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/repo/alerts.py backend/tests/test_alerts_repo.py
git commit -m "feat: add alert repository"
```

---

### Task 7: Listing repository with price history and search

**Files:**
- Create: `backend/apt/repo/listings.py`
- Test: `backend/tests/test_listings_repo.py`

**Interfaces:**
- Consumes: Task 4 fixture; `Listing`, `AlertFilters` from Task 2.
- Produces (`apt.repo.listings`):
  - `UpsertResult` (Pydantic model): `is_new: bool`, `price_changed: bool`, `old_price: int | None`.
  - `ListingRepo(conn)`:
    - `upsert(listing: Listing, now: datetime) -> UpsertResult` — insert new listings (writes first `price_history` row when price known); update existing ones (`last_seen`, fields; on price change appends `price_history`). The scraper cycle (plan 2) uses `is_new` / `price_changed` to decide notifications.
    - `get(listing_id: str) -> Listing | None`
    - `search(filters: AlertFilters, sort: Literal["newest", "price"] = "newest", limit: int = 50, offset: int = 0) -> list[Listing]` — the web search endpoint's engine (plan 4). Numeric/amenity/location filters applied in SQL with the same semantics as `listing_matches`, except unknown-value rows are excluded only when a bound on that field is set.
    - `price_history(listing_id: str) -> list[tuple[int, str]]` — `(price, observed_at)` oldest-first.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_listings_repo.py`:

```python
from datetime import datetime, timezone

from apt.domain.models import AlertFilters, Listing, Location
from apt.repo.listings import ListingRepo

T1 = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 7, 7, 12, 15, tzinfo=timezone.utc)


def make_listing(**overrides):
    base = dict(
        source="yad2",
        source_id="a1",
        url="https://example.com/a1",
        city="חיפה",
        neighborhood="הדר",
        price=5000,
        rooms=3.5,
        size_sqm=80,
        floor=2,
        has_mamad=True,
        has_elevator=False,
    )
    base.update(overrides)
    return Listing(**base)


def test_upsert_new_listing(conn):
    repo = ListingRepo(conn)
    result = repo.upsert(make_listing(), T1)
    assert result.is_new is True
    assert result.price_changed is False
    fetched = repo.get("yad2:a1")
    assert fetched.price == 5000
    assert fetched.city == "חיפה"
    assert repo.price_history("yad2:a1") == [(5000, T1.isoformat())]


def test_upsert_same_price_updates_last_seen_only(conn):
    repo = ListingRepo(conn)
    repo.upsert(make_listing(), T1)
    result = repo.upsert(make_listing(), T2)
    assert result.is_new is False
    assert result.price_changed is False
    assert len(repo.price_history("yad2:a1")) == 1


def test_upsert_price_change_appends_history(conn):
    repo = ListingRepo(conn)
    repo.upsert(make_listing(price=5000), T1)
    result = repo.upsert(make_listing(price=4500), T2)
    assert result.is_new is False
    assert result.price_changed is True
    assert result.old_price == 5000
    assert repo.get("yad2:a1").price == 4500
    assert repo.price_history("yad2:a1") == [(5000, T1.isoformat()), (4500, T2.isoformat())]


def test_get_missing_returns_none(conn):
    assert ListingRepo(conn).get("yad2:nope") is None


def seed_for_search(repo):
    repo.upsert(make_listing(source_id="cheap", price=4000, rooms=3.0), T1)
    repo.upsert(make_listing(source_id="pricey", price=7000, rooms=4.0), T1)
    repo.upsert(make_listing(source_id="tlv", city="תל אביב", neighborhood=None, price=6000), T2)
    repo.upsert(make_listing(source_id="nopricer", price=None), T2)


def test_search_no_filters_newest_first(conn):
    repo = ListingRepo(conn)
    seed_for_search(repo)
    results = repo.search(AlertFilters())
    assert len(results) == 4
    assert results[0].source_id in {"tlv", "nopricer"}


def test_search_price_filter_excludes_unknown_price(conn):
    repo = ListingRepo(conn)
    seed_for_search(repo)
    ids = {listing.source_id for listing in repo.search(AlertFilters(max_price=6000))}
    assert ids == {"cheap", "tlv"}


def test_search_by_location(conn):
    repo = ListingRepo(conn)
    seed_for_search(repo)
    haifa = repo.search(AlertFilters(locations=[Location(city="חיפה")]))
    assert {listing.source_id for listing in haifa} == {"cheap", "pricey", "nopricer"}
    hood = repo.search(AlertFilters(locations=[Location(city="חיפה", neighborhood="הדר")]))
    assert {listing.source_id for listing in hood} == {"cheap", "pricey", "nopricer"}


def test_search_amenity_and_rooms(conn):
    repo = ListingRepo(conn)
    seed_for_search(repo)
    ids = {
        listing.source_id
        for listing in repo.search(AlertFilters(require_mamad=True, min_rooms=3.5))
    }
    assert ids == {"pricey", "tlv", "nopricer"}


def test_search_sort_by_price_and_pagination(conn):
    repo = ListingRepo(conn)
    seed_for_search(repo)
    by_price = repo.search(AlertFilters(), sort="price")
    priced = [listing.source_id for listing in by_price if listing.price is not None]
    assert priced == ["cheap", "tlv", "pricey"]
    page = repo.search(AlertFilters(), limit=2, offset=2)
    assert len(page) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_listings_repo.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'apt.repo.listings'`.

- [ ] **Step 3: Implement the repository**

`backend/apt/repo/listings.py`:

```python
import json
import sqlite3
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from apt.domain.models import AlertFilters, Listing


class UpsertResult(BaseModel):
    is_new: bool
    price_changed: bool = False
    old_price: int | None = None


def _to_bool(value: int | None) -> bool | None:
    return None if value is None else bool(value)


def _row_to_listing(row: sqlite3.Row) -> Listing:
    return Listing(
        source=row["source"],
        source_id=row["source_id"],
        url=row["url"],
        city=row["city"],
        neighborhood=row["neighborhood"],
        street=row["street"],
        price=row["price"],
        rooms=row["rooms"],
        size_sqm=row["size_sqm"],
        floor=row["floor"],
        has_mamad=_to_bool(row["has_mamad"]),
        has_elevator=_to_bool(row["has_elevator"]),
        entry_date=date.fromisoformat(row["entry_date"]) if row["entry_date"] else None,
        tags=json.loads(row["tags"]),
        description=row["description"],
        photo_urls=json.loads(row["photo_urls"]),
    )


def _search_clauses(filters: AlertFilters) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if filters.locations:
        location_parts = []
        for loc in filters.locations:
            if loc.neighborhood is not None:
                location_parts.append("(city = ? AND neighborhood = ?)")
                params.extend([loc.city, loc.neighborhood])
            else:
                location_parts.append("city = ?")
                params.append(loc.city)
        clauses.append("(" + " OR ".join(location_parts) + ")")
    for column, low, high in (
        ("price", filters.min_price, filters.max_price),
        ("rooms", filters.min_rooms, filters.max_rooms),
        ("size_sqm", filters.min_size_sqm, None),
        ("floor", filters.min_floor, filters.max_floor),
    ):
        if low is not None:
            clauses.append(f"{column} >= ?")
            params.append(low)
        if high is not None:
            clauses.append(f"{column} <= ?")
            params.append(high)
    if filters.require_mamad:
        clauses.append("has_mamad = 1")
    if filters.require_elevator:
        clauses.append("has_elevator = 1")
    if filters.entry_by is not None:
        clauses.append("(entry_date IS NULL OR entry_date <= ?)")
        params.append(filters.entry_by.isoformat())
    where = " AND ".join(clauses) if clauses else "1=1"
    return where, params


class ListingRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def upsert(self, listing: Listing, now: datetime) -> UpsertResult:
        existing = self._conn.execute(
            "SELECT price FROM listings WHERE id = ?", (listing.id,)
        ).fetchone()
        timestamp = now.isoformat()
        values = (
            listing.url,
            listing.city,
            listing.neighborhood,
            listing.street,
            listing.price,
            listing.rooms,
            listing.size_sqm,
            listing.floor,
            None if listing.has_mamad is None else int(listing.has_mamad),
            None if listing.has_elevator is None else int(listing.has_elevator),
            listing.entry_date.isoformat() if listing.entry_date else None,
            json.dumps(listing.tags, ensure_ascii=False),
            listing.description,
            json.dumps(listing.photo_urls),
        )
        if existing is None:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO listings (
                        id, source, source_id, url, city, neighborhood, street,
                        price, rooms, size_sqm, floor, has_mamad, has_elevator,
                        entry_date, tags, description, photo_urls, first_seen, last_seen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (listing.id, listing.source, listing.source_id) + values + (timestamp, timestamp),
                )
                if listing.price is not None:
                    self._conn.execute(
                        "INSERT INTO price_history (listing_id, price, observed_at) VALUES (?, ?, ?)",
                        (listing.id, listing.price, timestamp),
                    )
            return UpsertResult(is_new=True)

        old_price = existing["price"]
        price_changed = listing.price is not None and listing.price != old_price
        with self._conn:
            self._conn.execute(
                """
                UPDATE listings SET
                    url = ?, city = ?, neighborhood = ?, street = ?,
                    price = ?, rooms = ?, size_sqm = ?, floor = ?,
                    has_mamad = ?, has_elevator = ?, entry_date = ?,
                    tags = ?, description = ?, photo_urls = ?, last_seen = ?
                WHERE id = ?
                """,
                values + (timestamp, listing.id),
            )
            if price_changed:
                self._conn.execute(
                    "INSERT INTO price_history (listing_id, price, observed_at) VALUES (?, ?, ?)",
                    (listing.id, listing.price, timestamp),
                )
        return UpsertResult(
            is_new=False,
            price_changed=price_changed,
            old_price=old_price if price_changed else None,
        )

    def get(self, listing_id: str) -> Listing | None:
        row = self._conn.execute(
            "SELECT * FROM listings WHERE id = ?", (listing_id,)
        ).fetchone()
        return _row_to_listing(row) if row else None

    def search(
        self,
        filters: AlertFilters,
        sort: Literal["newest", "price"] = "newest",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Listing]:
        where, params = _search_clauses(filters)
        order = "first_seen DESC" if sort == "newest" else "price IS NULL, price ASC"
        rows = self._conn.execute(
            f"SELECT * FROM listings WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [_row_to_listing(row) for row in rows]

    def price_history(self, listing_id: str) -> list[tuple[int, str]]:
        rows = self._conn.execute(
            "SELECT price, observed_at FROM price_history WHERE listing_id = ? ORDER BY id",
            (listing_id,),
        ).fetchall()
        return [(row["price"], row["observed_at"]) for row in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_listings_repo.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/repo/listings.py backend/tests/test_listings_repo.py
git commit -m "feat: add listing repository with price history and search"
```

---

### Task 8: Notification-dedup and source-state repositories

**Files:**
- Create: `backend/apt/repo/notifications.py`
- Create: `backend/apt/repo/source_state.py`
- Test: `backend/tests/test_notifications_repo.py`
- Test: `backend/tests/test_source_state_repo.py`

**Interfaces:**
- Consumes: Task 4 fixture; `UserRepo`, `AlertRepo`, `ListingRepo` (tests only).
- Produces:
  - `apt.repo.notifications.NotificationRepo(conn)`:
    - `claim(alert_id: int, listing_id: str, channel: str, now: datetime) -> bool` — atomically records the send; returns `False` if already recorded. **This is the exactly-once guarantee** (design D12): notifiers (plan 3) call `claim` first and send only on `True`.
    - `release(alert_id: int, listing_id: str, channel: str) -> None` — undo a claim when the actual send fails, so it retries next cycle.
  - `apt.repo.source_state.SourceStateRepo(conn)`:
    - `SourceState` (Pydantic model): `source: str`, `enabled: bool`, `last_run: str | None`, `last_success: str | None`, `last_error: str | None`.
    - `get(source: str) -> SourceState` — unknown source returns an enabled default row.
    - `set_enabled(source: str, enabled: bool) -> None` — the admin toggle (plan 4).
    - `record_run(source: str, now: datetime, error: str | None = None) -> None` — sets `last_run`; on success sets `last_success` and clears `last_error`, on failure records `last_error`.
    - `all() -> list[SourceState]` — the admin health page's query.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_notifications_repo.py`:

```python
from datetime import datetime, timezone

import pytest

from apt.domain.models import AlertFilters, Listing
from apt.repo.alerts import AlertRepo
from apt.repo.listings import ListingRepo
from apt.repo.notifications import NotificationRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def ids(conn):
    user = UserRepo(conn).upsert_google_user("g-1", "a@b.com", NOW)
    alert = AlertRepo(conn).create(user.id, "x", AlertFilters(), ["telegram"], NOW)
    listing = Listing(source="yad2", source_id="a1", url="https://e.com/a1", city="חיפה")
    ListingRepo(conn).upsert(listing, NOW)
    return alert.id, listing.id


def test_first_claim_wins_second_loses(conn, ids):
    repo = NotificationRepo(conn)
    alert_id, listing_id = ids
    assert repo.claim(alert_id, listing_id, "telegram", NOW) is True
    assert repo.claim(alert_id, listing_id, "telegram", NOW) is False


def test_different_channel_is_a_separate_claim(conn, ids):
    repo = NotificationRepo(conn)
    alert_id, listing_id = ids
    assert repo.claim(alert_id, listing_id, "telegram", NOW) is True
    assert repo.claim(alert_id, listing_id, "email", NOW) is True


def test_release_allows_reclaim(conn, ids):
    repo = NotificationRepo(conn)
    alert_id, listing_id = ids
    assert repo.claim(alert_id, listing_id, "telegram", NOW) is True
    repo.release(alert_id, listing_id, "telegram")
    assert repo.claim(alert_id, listing_id, "telegram", NOW) is True
```

`backend/tests/test_source_state_repo.py`:

```python
from datetime import datetime, timezone

from apt.repo.source_state import SourceStateRepo

T1 = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 7, 7, 12, 15, tzinfo=timezone.utc)


def test_unknown_source_defaults_to_enabled(conn):
    state = SourceStateRepo(conn).get("yad2")
    assert state.enabled is True
    assert state.last_run is None


def test_record_successful_run(conn):
    repo = SourceStateRepo(conn)
    repo.record_run("yad2", T1)
    state = repo.get("yad2")
    assert state.last_run == T1.isoformat()
    assert state.last_success == T1.isoformat()
    assert state.last_error is None


def test_record_failed_run_keeps_last_success(conn):
    repo = SourceStateRepo(conn)
    repo.record_run("yad2", T1)
    repo.record_run("yad2", T2, error="HTTP 403")
    state = repo.get("yad2")
    assert state.last_run == T2.isoformat()
    assert state.last_success == T1.isoformat()
    assert state.last_error == "HTTP 403"


def test_success_clears_previous_error(conn):
    repo = SourceStateRepo(conn)
    repo.record_run("facebook", T1, error="session expired")
    repo.record_run("facebook", T2)
    assert repo.get("facebook").last_error is None


def test_set_enabled_and_all(conn):
    repo = SourceStateRepo(conn)
    repo.record_run("yad2", T1)
    repo.set_enabled("facebook", False)
    assert repo.get("facebook").enabled is False
    assert {state.source for state in repo.all()} == {"yad2", "facebook"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_notifications_repo.py tests/test_source_state_repo.py -v
```

Expected: FAIL with `ModuleNotFoundError` for both new modules.

- [ ] **Step 3: Implement both repositories**

`backend/apt/repo/notifications.py`:

```python
import sqlite3
from datetime import datetime


class NotificationRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def claim(self, alert_id: int, listing_id: str, channel: str, now: datetime) -> bool:
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO sent_notifications (alert_id, listing_id, channel, sent_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (alert_id, listing_id, channel, now.isoformat()),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def release(self, alert_id: int, listing_id: str, channel: str) -> None:
        with self._conn:
            self._conn.execute(
                """
                DELETE FROM sent_notifications
                WHERE alert_id = ? AND listing_id = ? AND channel = ?
                """,
                (alert_id, listing_id, channel),
            )
```

`backend/apt/repo/source_state.py`:

```python
import sqlite3
from datetime import datetime

from pydantic import BaseModel


class SourceState(BaseModel):
    source: str
    enabled: bool = True
    last_run: str | None = None
    last_success: str | None = None
    last_error: str | None = None


def _row_to_state(row: sqlite3.Row) -> SourceState:
    return SourceState(
        source=row["source"],
        enabled=bool(row["enabled"]),
        last_run=row["last_run"],
        last_success=row["last_success"],
        last_error=row["last_error"],
    )


class SourceStateRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def _ensure_row(self, source: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO source_state (source) VALUES (?)", (source,)
        )

    def get(self, source: str) -> SourceState:
        row = self._conn.execute(
            "SELECT * FROM source_state WHERE source = ?", (source,)
        ).fetchone()
        return _row_to_state(row) if row else SourceState(source=source)

    def set_enabled(self, source: str, enabled: bool) -> None:
        with self._conn:
            self._ensure_row(source)
            self._conn.execute(
                "UPDATE source_state SET enabled = ? WHERE source = ?",
                (int(enabled), source),
            )

    def record_run(self, source: str, now: datetime, error: str | None = None) -> None:
        timestamp = now.isoformat()
        with self._conn:
            self._ensure_row(source)
            if error is None:
                self._conn.execute(
                    """
                    UPDATE source_state
                    SET last_run = ?, last_success = ?, last_error = NULL
                    WHERE source = ?
                    """,
                    (timestamp, timestamp, source),
                )
            else:
                self._conn.execute(
                    "UPDATE source_state SET last_run = ?, last_error = ? WHERE source = ?",
                    (timestamp, error, source),
                )

    def all(self) -> list[SourceState]:
        rows = self._conn.execute("SELECT * FROM source_state ORDER BY source").fetchall()
        return [_row_to_state(row) for row in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_notifications_repo.py tests/test_source_state_repo.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/repo/notifications.py backend/apt/repo/source_state.py \
        backend/tests/test_notifications_repo.py backend/tests/test_source_state_repo.py
git commit -m "feat: add notification-dedup and source-state repositories"
```

---

### Task 9: Scrape-set — coverage-driven location tracking

**Files:**
- Create: `backend/apt/repo/scrape_set.py`
- Test: `backend/tests/test_scrape_set.py`

**Interfaces:**
- Consumes: Task 4 fixture; `Location`, `AlertFilters` from Task 2; `AlertRepo`, `UserRepo` (implementation + tests).
- Produces (`apt.repo.scrape_set.ScrapeSetRepo(conn)`):
  - `log_search(location: Location, now: datetime) -> None` — called by the search API (plan 4) whenever someone searches a location.
  - `active_locations(now: datetime, max_age_days: int = 30) -> list[Location]` — deduplicated union of (a) locations in all **active** alerts and (b) locations searched within `max_age_days`. This is the scraper cycle's coverage input (plan 2, design D11).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_scrape_set.py`:

```python
from datetime import datetime, timedelta, timezone

from apt.domain.models import AlertFilters, Location
from apt.repo.alerts import AlertRepo
from apt.repo.scrape_set import ScrapeSetRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


def make_alert(conn, locations, active=True):
    user_repo = UserRepo(conn)
    user = user_repo.get_by_google_sub("g-1") or user_repo.upsert_google_user("g-1", "a@b.com", NOW)
    repo = AlertRepo(conn)
    alert = repo.create(user.id, "x", AlertFilters(locations=locations), ["telegram"], NOW)
    if not active:
        repo.set_active(alert.id, False)
    return alert


def test_empty_scrape_set(conn):
    assert ScrapeSetRepo(conn).active_locations(NOW) == []


def test_locations_from_active_alerts_only(conn):
    make_alert(conn, [Location(city="חיפה")])
    make_alert(conn, [Location(city="תל אביב")], active=False)
    locations = ScrapeSetRepo(conn).active_locations(NOW)
    assert locations == [Location(city="חיפה")]


def test_recent_searches_included_old_excluded(conn):
    repo = ScrapeSetRepo(conn)
    repo.log_search(Location(city="באר שבע"), NOW - timedelta(days=5))
    repo.log_search(Location(city="אילת"), NOW - timedelta(days=45))
    locations = repo.active_locations(NOW)
    assert Location(city="באר שבע") in locations
    assert Location(city="אילת") not in locations


def test_union_is_deduplicated(conn):
    repo = ScrapeSetRepo(conn)
    make_alert(conn, [Location(city="חיפה", neighborhood="הדר"), Location(city="חיפה")])
    repo.log_search(Location(city="חיפה"), NOW)
    repo.log_search(Location(city="חיפה", neighborhood="הדר"), NOW)
    locations = repo.active_locations(NOW)
    assert len(locations) == 2
    assert set((loc.city, loc.neighborhood) for loc in locations) == {
        ("חיפה", None),
        ("חיפה", "הדר"),
    }
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_scrape_set.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'apt.repo.scrape_set'`.

- [ ] **Step 3: Implement the scrape-set repository**

`backend/apt/repo/scrape_set.py`:

```python
import sqlite3
from datetime import datetime, timedelta

from apt.domain.models import Location
from apt.repo.alerts import AlertRepo


class ScrapeSetRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def log_search(self, location: Location, now: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO search_log (city, neighborhood, searched_at) VALUES (?, ?, ?)",
                (location.city, location.neighborhood, now.isoformat()),
            )

    def active_locations(self, now: datetime, max_age_days: int = 30) -> list[Location]:
        seen: set[tuple[str, str | None]] = set()
        result: list[Location] = []

        def add(location: Location) -> None:
            key = (location.city, location.neighborhood)
            if key not in seen:
                seen.add(key)
                result.append(location)

        for alert in AlertRepo(self._conn).list_active():
            for location in alert.filters.locations:
                add(location)

        cutoff = (now - timedelta(days=max_age_days)).isoformat()
        rows = self._conn.execute(
            "SELECT DISTINCT city, neighborhood FROM search_log WHERE searched_at >= ?",
            (cutoff,),
        ).fetchall()
        for row in rows:
            add(Location(city=row["city"], neighborhood=row["neighborhood"]))
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_scrape_set.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run the full suite and commit**

```bash
pytest -v
```

Expected: all tests from Tasks 1–9 PASS.

```bash
cd /Users/alon.i/APT
git add backend/apt/repo/scrape_set.py backend/tests/test_scrape_set.py
git commit -m "feat: add coverage-driven scrape-set repository"
```

---

### Task 10: WAL concurrency smoke test + backend README

**Files:**
- Create: `backend/README.md`
- Test: `backend/tests/test_concurrency.py`

**Interfaces:**
- Consumes: everything above.
- Produces: proof the "parallel usage" requirement holds at the DB layer (reader in one connection/thread while a writer writes), and developer docs for the backend.

- [ ] **Step 1: Write the concurrency test**

`backend/tests/test_concurrency.py`:

```python
import threading
from datetime import datetime, timezone

from apt.domain.models import Listing
from apt.repo.db import connect, migrate
from apt.repo.listings import ListingRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


def test_reader_not_blocked_while_writer_writes(tmp_path):
    db_path = tmp_path / "concurrent.db"
    setup = connect(db_path)
    migrate(setup)
    ListingRepo(setup).upsert(
        Listing(source="yad2", source_id="seed", url="https://e.com/s", city="חיפה"),
        NOW,
    )
    setup.close()

    errors: list[Exception] = []

    def writer():
        try:
            conn = connect(db_path)
            repo = ListingRepo(conn)
            for i in range(50):
                repo.upsert(
                    Listing(source="yad2", source_id=f"w{i}", url=f"https://e.com/{i}", city="חיפה"),
                    NOW,
                )
            conn.close()
        except Exception as exc:
            errors.append(exc)

    def reader():
        try:
            conn = connect(db_path)
            repo = ListingRepo(conn)
            for _ in range(50):
                assert repo.get("yad2:seed") is not None
            conn.close()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
```

- [ ] **Step 2: Run the test**

```bash
pytest tests/test_concurrency.py -v
```

Expected: PASS (WAL allows the reader to proceed during writes). If it fails with `database is locked`, WAL is not enabled — recheck `connect()`.

- [ ] **Step 3: Write the backend README**

`backend/README.md`:

```markdown
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
```

- [ ] **Step 4: Update the repo root README**

Replace the content of `/Users/alon.i/APT/README.md` with:

```markdown
# APT

Apartment rental search service for Israel: a Hebrew web UI + Telegram bot that
collects listings from Yad2 (and best-effort Facebook) and alerts users the
moment new listings match their saved searches.

- **Specs:** `docs/superpowers/specs/`
- **Implementation plans:** `docs/superpowers/plans/`
- **Backend:** `backend/` (Python 3.12, FastAPI later; see `backend/README.md`)
```

- [ ] **Step 5: Run the full suite and commit**

```bash
cd /Users/alon.i/APT/backend && source .venv/bin/activate && pytest -v
```

Expected: all PASS.

```bash
cd /Users/alon.i/APT
git add backend/tests/test_concurrency.py backend/README.md README.md
git commit -m "test: prove WAL concurrency; add backend and root READMEs"
```

---

## Plan 1 Exit Criteria

- `pytest` green across all tasks.
- `apt.domain` + `apt.repo` provide every interface plans 2–4 consume: `listing_matches`, `UserRepo`, `AlertRepo`, `ListingRepo.upsert/search/price_history`, `NotificationRepo.claim/release`, `SourceStateRepo`, `ScrapeSetRepo.active_locations`.
- No service processes yet — that is plan 2 (`scraper`), plan 3 (`bot` + notify), plan 4 (`web`).
