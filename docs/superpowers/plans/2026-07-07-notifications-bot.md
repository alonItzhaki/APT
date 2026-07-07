# APT Plan 3/6: Notifications + Telegram Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the LogNotifier placeholder with real delivery: Telegram + email channels behind an exactly-once claim, plus the user-facing Telegram bot (account linking, latest matches, pause/resume).

**Architecture:** Schema migration v2 widens the exactly-once key to `(alert, listing, channel, kind, price_key)` so repeated price drops re-notify per new price, and adds `link_tokens` for web→bot account linking (tokens minted by plan 4's API, consumed by the bot). `apt.notify` gains pure Hebrew formatting, a `Channel` protocol, `ChannelNotifier` (claims, delivers, releases on failure, never raises — plan 2's cycle requires it), and Telegram/email channel implementations. `apt.bot` holds the command handlers; `apt.bot_main` is the polling process; `scraper_main` switches to `ChannelNotifier` when a bot token is configured.

**Tech Stack:** python-telegram-bot ≥22 (polling, HTML messages), Brevo transactional email REST API (free tier 300/day — satisfies the spec's ≥100/day), aiohttp.

## Global Constraints

- All plan-1/2 constraints hold. New runtime dep: `python-telegram-bot>=22`.
- Channels are exactly `"telegram"` and `"email"`; kinds exactly `"new"` and `"price_drop"`.
- **`ChannelNotifier.send` NEVER raises** (plan-2 contract: an exception between upsert and send loses events); claim BEFORE delivering; release the claim on delivery failure so the next cycle retries.
- `price_key` in the claim: `0` for kind `"new"`, the listing's current price for `"price_drop"` (re-drop to a new price re-notifies; same price never re-sends).
- Services (not repos) may read the clock only via an injectable `now_fn` defaulting to `lambda: datetime.now(timezone.utc)` — tests inject fixed times.
- Migration scripts must not embed `;` inside string literals (migrate() splits on `;`).
- User-visible copy is Hebrew; all user-originated content HTML-escaped before Telegram/email HTML.
- Secrets/env: `TELEGRAM_BOT_TOKEN`, `BREVO_API_KEY`, `APT_EMAIL_FROM` — read at entrypoint/construction, never hardcoded.
- No test performs network I/O — python-telegram-bot's `Bot` and aiohttp are always mocked (aioresponses is unusable with aiohttp 3.14; mock `ClientSession` like `tests/test_yad2_source.py` does).
- Work from `/Users/alon.i/APT/backend` with `.venv` activated (`uv pip install -e '.[dev]'` after pyproject changes); commits from `/Users/alon.i/APT`; no Co-Authored-By.

---

### Task 1: Migration v2 — widened claim key + link tokens; repo updates

**Files:**
- Modify: `backend/apt/repo/db.py` (append migration v2 to `MIGRATIONS`)
- Modify: `backend/apt/repo/notifications.py` (new claim/release signatures)
- Modify: `backend/tests/test_notifications_repo.py` (update to new signatures + new cases)
- Modify: `backend/tests/test_db.py` (expected tables + user_version)
- Create: `backend/apt/repo/link_tokens.py`
- Test: `backend/tests/test_link_tokens.py`

**Interfaces:**
- Consumes: plan-1 `connect`/`migrate`/`MIGRATIONS`, `UserRepo`.
- Produces:
  - Migration v2: `sent_notifications` rebuilt with columns `(alert_id, listing_id, channel, kind TEXT NOT NULL DEFAULT 'new', price_key INTEGER NOT NULL DEFAULT 0, sent_at)`, PRIMARY KEY `(alert_id, listing_id, channel, kind, price_key)`, same FK cascades; existing rows preserved as kind='new'/price_key=0. New table `link_tokens(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, created_at TEXT NOT NULL, used_at TEXT)`.
  - `NotificationRepo.claim(alert_id: int, listing_id: str, channel: str, kind: str, price_key: int, now: datetime) -> bool` and `release(alert_id, listing_id, channel, kind, price_key) -> None` (same exactly-once semantics, wider key).
  - `LinkTokenRepo(conn)`: `create(token: str, user_id: int, now: datetime) -> None`; `consume(token: str, now: datetime, max_age_minutes: int = 15) -> int | None` — returns the user_id and marks used; None when missing, already used, or older than max_age.

- [ ] **Step 1: Update the failing tests first**

Rewrite `backend/tests/test_notifications_repo.py` to:

```python
from datetime import datetime, timezone

import pytest
import sqlite3

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
    assert repo.claim(alert_id, listing_id, "telegram", "new", 0, NOW) is True
    assert repo.claim(alert_id, listing_id, "telegram", "new", 0, NOW) is False


def test_different_channel_kind_or_price_is_a_separate_claim(conn, ids):
    repo = NotificationRepo(conn)
    alert_id, listing_id = ids
    assert repo.claim(alert_id, listing_id, "telegram", "new", 0, NOW) is True
    assert repo.claim(alert_id, listing_id, "email", "new", 0, NOW) is True
    assert repo.claim(alert_id, listing_id, "telegram", "price_drop", 4500, NOW) is True
    assert repo.claim(alert_id, listing_id, "telegram", "price_drop", 4500, NOW) is False
    assert repo.claim(alert_id, listing_id, "telegram", "price_drop", 4200, NOW) is True


def test_release_allows_reclaim(conn, ids):
    repo = NotificationRepo(conn)
    alert_id, listing_id = ids
    assert repo.claim(alert_id, listing_id, "telegram", "new", 0, NOW) is True
    repo.release(alert_id, listing_id, "telegram", "new", 0)
    assert repo.claim(alert_id, listing_id, "telegram", "new", 0, NOW) is True


def test_claim_with_unknown_alert_raises(conn, ids):
    repo = NotificationRepo(conn)
    _, listing_id = ids
    with pytest.raises(sqlite3.IntegrityError):
        repo.claim(999999, listing_id, "telegram", "new", 0, NOW)
```

In `backend/tests/test_db.py`: add `"link_tokens"` to `EXPECTED_TABLES` and change the idempotency assertion to `user_version == 2` (also update `test_migrate_atomicity`'s final expectation if it asserts a specific version — it patches MIGRATIONS itself, check and keep its logic intact).

Create `backend/tests/test_link_tokens.py`:

```python
from datetime import datetime, timedelta, timezone

from apt.repo.link_tokens import LinkTokenRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


def make_user(conn):
    return UserRepo(conn).upsert_google_user("g-1", "a@b.com", NOW)


def test_consume_valid_token_once(conn):
    user = make_user(conn)
    repo = LinkTokenRepo(conn)
    repo.create("tok-1", user.id, NOW)
    assert repo.consume("tok-1", NOW + timedelta(minutes=5)) == user.id
    assert repo.consume("tok-1", NOW + timedelta(minutes=6)) is None


def test_consume_unknown_token(conn):
    assert LinkTokenRepo(conn).consume("nope", NOW) is None


def test_consume_expired_token(conn):
    user = make_user(conn)
    repo = LinkTokenRepo(conn)
    repo.create("tok-1", user.id, NOW)
    assert repo.consume("tok-1", NOW + timedelta(minutes=16)) is None
```

- [ ] **Step 2: Run to verify failures**

`pytest tests/test_notifications_repo.py tests/test_link_tokens.py tests/test_db.py -v` — notification tests fail (signature), link-token tests fail (module missing), db tests fail (missing table / version).

- [ ] **Step 3: Implement**

Append to `MIGRATIONS` in `backend/apt/repo/db.py` (as a SECOND list element — never edit v1):

```python
    # v2: exactly-once key widened with (kind, price_key); link tokens for web->bot linking
    """
    CREATE TABLE sent_notifications_v2 (
        alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
        listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
        channel TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'new',
        price_key INTEGER NOT NULL DEFAULT 0,
        sent_at TEXT NOT NULL,
        PRIMARY KEY (alert_id, listing_id, channel, kind, price_key)
    );

    INSERT INTO sent_notifications_v2 (alert_id, listing_id, channel, sent_at)
        SELECT alert_id, listing_id, channel, sent_at FROM sent_notifications;

    DROP TABLE sent_notifications;

    ALTER TABLE sent_notifications_v2 RENAME TO sent_notifications;

    CREATE TABLE link_tokens (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        used_at TEXT
    );
    """,
```

Rewrite `backend/apt/repo/notifications.py`:

```python
import sqlite3
from datetime import datetime


class NotificationRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def claim(
        self,
        alert_id: int,
        listing_id: str,
        channel: str,
        kind: str,
        price_key: int,
        now: datetime,
    ) -> bool:
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO sent_notifications
                        (alert_id, listing_id, channel, kind, price_key, sent_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (alert_id, listing_id, channel, kind, price_key, now.isoformat()),
                )
            return True
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed" in str(exc):
                return False
            raise

    def release(
        self, alert_id: int, listing_id: str, channel: str, kind: str, price_key: int
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                DELETE FROM sent_notifications
                WHERE alert_id = ? AND listing_id = ? AND channel = ?
                  AND kind = ? AND price_key = ?
                """,
                (alert_id, listing_id, channel, kind, price_key),
            )
```

Create `backend/apt/repo/link_tokens.py`:

```python
import sqlite3
from datetime import datetime, timedelta


class LinkTokenRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, token: str, user_id: int, now: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO link_tokens (token, user_id, created_at) VALUES (?, ?, ?)",
                (token, user_id, now.isoformat()),
            )

    def consume(self, token: str, now: datetime, max_age_minutes: int = 15) -> int | None:
        row = self._conn.execute(
            "SELECT user_id, created_at, used_at FROM link_tokens WHERE token = ?",
            (token,),
        ).fetchone()
        if row is None or row["used_at"] is not None:
            return None
        created = datetime.fromisoformat(row["created_at"])
        if now - created > timedelta(minutes=max_age_minutes):
            return None
        with self._conn:
            self._conn.execute(
                "UPDATE link_tokens SET used_at = ? WHERE token = ?",
                (now.isoformat(), token),
            )
        return row["user_id"]
```

- [ ] **Step 4: Run the full suite; fix any other claim() callers (there are none in production code — LogNotifier doesn't claim); all green**

`pytest -v` — everything passes.

- [ ] **Step 5: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/repo/db.py backend/apt/repo/notifications.py backend/apt/repo/link_tokens.py \
        backend/tests/test_notifications_repo.py backend/tests/test_link_tokens.py backend/tests/test_db.py
git commit -m "feat: widen exactly-once key with kind and price, add link tokens (schema v2)"
```

---

### Task 2: Hebrew message formatting (pure)

**Files:**
- Create: `backend/apt/notify/format.py`
- Test: `backend/tests/test_format.py`

**Interfaces:**
- Consumes: `MatchEvent` (plan 2).
- Produces (`apt.notify.format`):
  - `telegram_message(event: MatchEvent) -> str` — Telegram-HTML: bold header 🏠 דירה חדשה! for new / 🔻 ירידת מחיר! with old→new for drops; lines for price (₪ thousands separators), location (street, neighborhood, city — non-empty parts), rooms/size/floor, ממ"ד/מעלית as כן/לא/לא ידוע, description trimmed to 400 chars, and an `<a href>` link. All listing text HTML-escaped.
  - `email_subject(event: MatchEvent) -> str` — e.g. `דירה חדשה: 3.5 חד' בחיפה - ₪5,000` / `ירידת מחיר: ...`.
  - `email_html(event: MatchEvent) -> str` — simple `dir="rtl"` HTML document with the same fields and link.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_format.py`:

```python
from apt.domain.events import MatchEvent
from apt.domain.models import Alert, AlertFilters, Listing
from apt.notify.format import email_html, email_subject, telegram_message


def make_event(kind="new", old_price=None, **listing_overrides):
    base = dict(
        source="yad2", source_id="a1", url="https://yad2.co.il/item/a1",
        city="חיפה", neighborhood="הדר", street="הרצל", price=5000,
        rooms=3.5, size_sqm=80, floor=2, has_mamad=True, has_elevator=None,
        description="דירה יפה <b>מאוד</b>",
    )
    base.update(listing_overrides)
    alert = Alert(id=1, user_id=1, name="חיפוש", filters=AlertFilters(), channels=["telegram"])
    return MatchEvent(kind=kind, listing=Listing(**base), alert=alert, old_price=old_price)


def test_telegram_new_message():
    text = telegram_message(make_event())
    assert "דירה חדשה" in text
    assert "₪5,000" in text
    assert "הרצל, הדר, חיפה" in text
    assert "3.5" in text and "80" in text
    assert 'ממ"ד: כן' in text
    assert "מעלית: לא ידוע" in text
    assert '<a href="https://yad2.co.il/item/a1">' in text
    assert "&lt;b&gt;מאוד&lt;/b&gt;" in text  # description escaped


def test_telegram_price_drop_message():
    text = telegram_message(make_event(kind="price_drop", old_price=6000, price=5000))
    assert "ירידת מחיר" in text
    assert "₪6,000" in text and "₪5,000" in text


def test_telegram_handles_missing_fields():
    text = telegram_message(make_event(price=None, rooms=None, size_sqm=None,
                                       floor=None, street=None, neighborhood=None,
                                       has_mamad=None, description=""))
    assert "חיפה" in text
    assert "לא ידוע" in text


def test_description_trimmed():
    text = telegram_message(make_event(description="א" * 500))
    assert "א" * 400 + "..." in text
    assert "א" * 401 not in text


def test_email_subject_and_html():
    event = make_event()
    assert "חיפה" in email_subject(event)
    html = email_html(event)
    assert 'dir="rtl"' in html
    assert "₪5,000" in html
    assert "https://yad2.co.il/item/a1" in html
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_format.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`backend/apt/notify/format.py`:

```python
import html

from apt.domain.events import MatchEvent
from apt.domain.models import Listing

MAX_DESCRIPTION_CHARS = 400
UNKNOWN = "לא ידוע"


def _escape(value: object) -> str:
    return html.escape(str(value), quote=False)


def _price(value: int | None) -> str:
    return f"₪{value:,}" if value is not None else UNKNOWN


def _location(listing: Listing) -> str:
    parts = [part for part in (listing.street, listing.neighborhood, listing.city) if part]
    return ", ".join(dict.fromkeys(parts))


def _yes_no(value: bool | None) -> str:
    if value is True:
        return "כן"
    if value is False:
        return "לא"
    return UNKNOWN


def _maybe(value: object) -> str:
    return _escape(value) if value is not None else UNKNOWN


def _description(listing: Listing) -> str:
    text = listing.description
    if len(text) > MAX_DESCRIPTION_CHARS:
        text = text[:MAX_DESCRIPTION_CHARS].rstrip() + "..."
    return _escape(text)


def _header(event: MatchEvent) -> str:
    if event.kind == "price_drop":
        return f"🔻 ירידת מחיר! {_price(event.old_price)} ← {_price(event.listing.price)}"
    return "🏠 דירה חדשה!"


def _lines(event: MatchEvent) -> list[str]:
    listing = event.listing
    lines = [
        f"<b>{_header(event)}</b>",
        f"מחיר: {_price(listing.price)}",
        f"מיקום: {_escape(_location(listing))}",
        f"חדרים: {_maybe(listing.rooms)} | גודל: {_maybe(listing.size_sqm)} מ\"ר | קומה: {_maybe(listing.floor)}",
        f'ממ"ד: {_yes_no(listing.has_mamad)} | מעלית: {_yes_no(listing.has_elevator)}',
    ]
    if listing.description:
        lines.append(_description(listing))
    lines.append(f'<a href="{html.escape(listing.url, quote=True)}">לצפייה במודעה</a>')
    return lines


def telegram_message(event: MatchEvent) -> str:
    return "\n".join(_lines(event))


def email_subject(event: MatchEvent) -> str:
    listing = event.listing
    prefix = "ירידת מחיר" if event.kind == "price_drop" else "דירה חדשה"
    rooms = f"{listing.rooms} חד' " if listing.rooms is not None else ""
    return f"{prefix}: {rooms}ב{listing.city} - {_price(listing.price)}"


def email_html(event: MatchEvent) -> str:
    body = "<br>\n".join(_lines(event))
    return f'<!DOCTYPE html>\n<html dir="rtl" lang="he"><body>\n{body}\n</body></html>'
```

- [ ] **Step 4: Run to verify pass** — `pytest tests/test_format.py -v` → all PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/notify/format.py backend/tests/test_format.py
git commit -m "feat: add hebrew notification formatting"
```

---

### Task 3: Channel protocol + ChannelNotifier

**Files:**
- Create: `backend/apt/notify/notifier.py`
- Test: `backend/tests/test_notifier.py`

**Interfaces:**
- Consumes: `NotificationRepo` (Task 1 signatures), `UserRepo`, `MatchEvent`.
- Produces (`apt.notify.notifier`):
  - `Channel` (Protocol): `name: str`; `applicable(user: User) -> bool`; `async deliver(user: User, event: MatchEvent) -> None` (raise on failure).
  - `price_key_for(event: MatchEvent) -> int` — 0 for "new", `event.listing.price or 0` for "price_drop".
  - `ChannelNotifier(conn, channels: dict[str, Channel], now_fn=None)` satisfying plan 2's `Notifier` protocol:
    - resolves the alert's user (missing user → log + return);
    - for each of `event.alert.channels`: unknown channel name or not `applicable(user)` → skip; `claim(...)` False → skip; deliver; on delivery exception → log + `release(...)`;
    - catches ALL exceptions internally — `send` never raises.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_notifier.py`:

```python
from datetime import datetime, timezone

from apt.domain.events import MatchEvent
from apt.domain.models import Alert, AlertFilters, Listing
from apt.notify.notifier import ChannelNotifier, price_key_for
from apt.repo.alerts import AlertRepo
from apt.repo.listings import ListingRepo
from apt.repo.notifications import NotificationRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


class FakeChannel:
    def __init__(self, name, applicable=True, fail=False):
        self.name = name
        self._applicable = applicable
        self._fail = fail
        self.delivered = []

    def applicable(self, user):
        return self._applicable

    async def deliver(self, user, event):
        if self._fail:
            raise RuntimeError("boom")
        self.delivered.append((user.id, event.listing.id))


def setup(conn, channels=("telegram",)):
    user = UserRepo(conn).upsert_google_user("g-1", "a@b.com", NOW)
    UserRepo(conn).set_telegram_chat(user.id, 42)
    alert = AlertRepo(conn).create(user.id, "x", AlertFilters(), list(channels), NOW)
    listing = Listing(source="yad2", source_id="a1", url="https://e.com/a1", city="חיפה", price=5000)
    ListingRepo(conn).upsert(listing, NOW)
    return user, alert, listing


def make_event(alert, listing, kind="new", old_price=None):
    return MatchEvent(kind=kind, listing=listing, alert=alert, old_price=old_price)


def make_bare_event(kind, price):
    listing = Listing(source="yad2", source_id="x", url="https://e.com/x", city="a", price=price)
    alert = Alert(id=1, user_id=1, name="n", filters=AlertFilters(), channels=["telegram"])
    return MatchEvent(kind=kind, listing=listing, alert=alert)


def test_price_key_for():
    assert price_key_for(make_bare_event("new", 5000)) == 0
    assert price_key_for(make_bare_event("price_drop", 4500)) == 4500
    assert price_key_for(make_bare_event("price_drop", None)) == 0


async def test_delivers_once_per_channel(conn):
    user, alert, listing = setup(conn, channels=("telegram", "email"))
    telegram, email = FakeChannel("telegram"), FakeChannel("email")
    notifier = ChannelNotifier(conn, {"telegram": telegram, "email": email}, now_fn=lambda: NOW)
    await notifier.send(make_event(alert, listing))
    await notifier.send(make_event(alert, listing))  # duplicate cycle
    assert telegram.delivered == [(user.id, listing.id)]
    assert email.delivered == [(user.id, listing.id)]


async def test_inapplicable_channel_skipped_without_claim(conn):
    user, alert, listing = setup(conn)
    channel = FakeChannel("telegram", applicable=False)
    notifier = ChannelNotifier(conn, {"telegram": channel}, now_fn=lambda: NOW)
    await notifier.send(make_event(alert, listing))
    assert channel.delivered == []
    assert NotificationRepo(conn).claim(alert.id, listing.id, "telegram", "new", 0, NOW) is True


async def test_delivery_failure_releases_claim_and_does_not_raise(conn):
    user, alert, listing = setup(conn)
    failing = FakeChannel("telegram", fail=True)
    notifier = ChannelNotifier(conn, {"telegram": failing}, now_fn=lambda: NOW)
    await notifier.send(make_event(alert, listing))  # must not raise
    working = FakeChannel("telegram")
    notifier2 = ChannelNotifier(conn, {"telegram": working}, now_fn=lambda: NOW)
    await notifier2.send(make_event(alert, listing))
    assert working.delivered == [(user.id, listing.id)]


async def test_unknown_channel_name_ignored(conn):
    user, alert, listing = setup(conn, channels=("telegram",))
    notifier = ChannelNotifier(conn, {}, now_fn=lambda: NOW)
    await notifier.send(make_event(alert, listing))  # must not raise


async def test_price_drop_renotifies_only_new_price(conn):
    user, alert, listing = setup(conn)
    channel = FakeChannel("telegram")
    notifier = ChannelNotifier(conn, {"telegram": channel}, now_fn=lambda: NOW)
    drop = make_event(alert, listing.model_copy(update={"price": 4500}), kind="price_drop", old_price=5000)
    await notifier.send(drop)
    await notifier.send(drop)
    deeper = make_event(alert, listing.model_copy(update={"price": 4000}), kind="price_drop", old_price=4500)
    await notifier.send(deeper)
    assert len(channel.delivered) == 2
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_notifier.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`backend/apt/notify/notifier.py`:

```python
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Callable, Protocol

from apt.domain.events import MatchEvent
from apt.domain.models import User
from apt.repo.notifications import NotificationRepo
from apt.repo.users import UserRepo

logger = logging.getLogger(__name__)


class Channel(Protocol):
    name: str

    def applicable(self, user: User) -> bool: ...

    async def deliver(self, user: User, event: MatchEvent) -> None: ...


def price_key_for(event: MatchEvent) -> int:
    if event.kind == "price_drop":
        return event.listing.price or 0
    return 0


class ChannelNotifier:
    """Claims exactly-once per (alert, listing, channel, kind, price) and delivers.

    send() never raises: the cycle has already recorded the listing, so an
    escaping exception would silently drop every remaining notification.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        channels: dict[str, Channel],
        now_fn: Callable[[], datetime] | None = None,
    ):
        self._conn = conn
        self._channels = channels
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    async def send(self, event: MatchEvent) -> None:
        try:
            await self._send(event)
        except Exception:
            logger.exception("notifier: unexpected failure for listing %s", event.listing.id)

    async def _send(self, event: MatchEvent) -> None:
        user = UserRepo(self._conn).get(event.alert.user_id)
        if user is None:
            logger.warning("notifier: user %s gone, skipping", event.alert.user_id)
            return
        notifications = NotificationRepo(self._conn)
        price_key = price_key_for(event)
        for channel_name in event.alert.channels:
            channel = self._channels.get(channel_name)
            if channel is None or not channel.applicable(user):
                continue
            if not notifications.claim(
                event.alert.id, event.listing.id, channel_name, event.kind, price_key, self._now_fn()
            ):
                continue
            try:
                await channel.deliver(user, event)
            except Exception as exc:
                logger.error(
                    "notifier: %s delivery failed for listing %s: %s",
                    channel_name, event.listing.id, exc,
                )
                notifications.release(
                    event.alert.id, event.listing.id, channel_name, event.kind, price_key
                )
```

- [ ] **Step 4: Run to verify pass, then full suite** — `pytest tests/test_notifier.py -v` then `pytest`.

- [ ] **Step 5: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/notify/notifier.py backend/tests/test_notifier.py
git commit -m "feat: add channel notifier with exactly-once claims"
```

---

### Task 4: Telegram channel

**Files:**
- Modify: `backend/pyproject.toml` (add `python-telegram-bot>=22` to dependencies; reinstall)
- Create: `backend/apt/notify/telegram_channel.py`
- Test: `backend/tests/test_telegram_channel.py`

**Interfaces:**
- Consumes: `telegram_message` (Task 2); `Channel` shape (Task 3); `UserRepo` (for unlinking blocked users).
- Produces (`apt.notify.telegram_channel.TelegramChannel(conn, bot)`):
  - `name = "telegram"`; `applicable(user)` → `user.telegram_chat_id is not None`.
  - `deliver(user, event)`: `bot.send_message(chat_id=..., text=telegram_message(event), parse_mode="HTML", disable_web_page_preview=False)`.
  - On `telegram.error.RetryAfter`: sleep `retry_after + 1`, retry once; second failure propagates (notifier releases the claim → retried next cycle).
  - On `telegram.error.Forbidden` (user blocked the bot / chat gone): clear the user's `telegram_chat_id` via `UserRepo.set_telegram_chat(user.id, None)`, log, and return WITHOUT raising (no point retrying a blocked chat; claim stays consumed).
  - Constructed with an already-built `telegram.Bot` (entrypoints own the token).

- [ ] **Step 1: Update pyproject and install**

Add `"python-telegram-bot>=22",` to `[project] dependencies`. Run `uv pip install -e '.[dev]'`.

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_telegram_channel.py`:

```python
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from telegram.error import Forbidden, RetryAfter

from apt.domain.events import MatchEvent
from apt.domain.models import AlertFilters, Listing, User
from apt.notify.telegram_channel import TelegramChannel
from apt.repo.alerts import AlertRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


def make_event(conn):
    user = UserRepo(conn).upsert_google_user("g-1", "a@b.com", NOW)
    UserRepo(conn).set_telegram_chat(user.id, 42)
    alert = AlertRepo(conn).create(user.id, "x", AlertFilters(), ["telegram"], NOW)
    listing = Listing(source="yad2", source_id="a1", url="https://e.com/a1", city="חיפה", price=5000)
    return UserRepo(conn).get(user.id), MatchEvent(kind="new", listing=listing, alert=alert)


def test_applicable(conn):
    channel = TelegramChannel(conn, AsyncMock())
    assert channel.applicable(User(id=1, google_sub="g", email="e", telegram_chat_id=5)) is True
    assert channel.applicable(User(id=1, google_sub="g", email="e")) is False


async def test_deliver_sends_html(conn):
    bot = AsyncMock()
    user, event = make_event(conn)
    await TelegramChannel(conn, bot).deliver(user, event)
    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == 42
    assert kwargs["parse_mode"] == "HTML"
    assert "₪5,000" in kwargs["text"]


async def test_retry_after_then_success(conn, monkeypatch):
    import apt.notify.telegram_channel as mod
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    bot = AsyncMock()
    bot.send_message.side_effect = [RetryAfter(3), None]
    user, event = make_event(conn)
    await TelegramChannel(conn, bot).deliver(user, event)
    assert bot.send_message.call_count == 2
    assert sleeps == [4]


async def test_forbidden_unlinks_user_without_raising(conn):
    bot = AsyncMock()
    bot.send_message.side_effect = Forbidden("blocked")
    user, event = make_event(conn)
    await TelegramChannel(conn, bot).deliver(user, event)
    assert UserRepo(conn).get(user.id).telegram_chat_id is None


async def test_other_errors_propagate(conn):
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("network down")
    user, event = make_event(conn)
    with pytest.raises(RuntimeError):
        await TelegramChannel(conn, bot).deliver(user, event)
```

- [ ] **Step 3: Run to verify failure** — `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

`backend/apt/notify/telegram_channel.py`:

```python
import asyncio
import logging
import sqlite3

from telegram import Bot
from telegram.error import Forbidden, RetryAfter

from apt.domain.events import MatchEvent
from apt.domain.models import User
from apt.notify.format import telegram_message
from apt.repo.users import UserRepo

logger = logging.getLogger(__name__)


class TelegramChannel:
    name = "telegram"

    def __init__(self, conn: sqlite3.Connection, bot: Bot):
        self._conn = conn
        self._bot = bot

    def applicable(self, user: User) -> bool:
        return user.telegram_chat_id is not None

    async def deliver(self, user: User, event: MatchEvent) -> None:
        text = telegram_message(event)
        try:
            await self._send(user.telegram_chat_id, text)
        except Forbidden:
            # Blocked chats never succeed on retry; unlink instead.
            logger.info("telegram: chat %s blocked us, unlinking user %s", user.telegram_chat_id, user.id)
            UserRepo(self._conn).set_telegram_chat(user.id, None)

    async def _send(self, chat_id: int, text: str) -> None:
        try:
            await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
```

- [ ] **Step 5: Run to verify pass, then full suite; commit**

```bash
cd /Users/alon.i/APT
git add backend/pyproject.toml backend/apt/notify/telegram_channel.py backend/tests/test_telegram_channel.py
git commit -m "feat: add telegram delivery channel"
```

---

### Task 5: Email channel (Brevo)

**Files:**
- Create: `backend/apt/notify/email_channel.py`
- Test: `backend/tests/test_email_channel.py`

**Interfaces:**
- Consumes: `email_subject`/`email_html` (Task 2); `Channel` shape.
- Produces (`apt.notify.email_channel.EmailChannel(api_key: str, from_email: str)`):
  - `name = "email"`; `applicable(user)` → `bool(user.email)`.
  - `deliver(user, event)`: POST `https://api.brevo.com/v3/smtp/email` with header `{"api-key": api_key}` and JSON `{"sender": {"email": from_email, "name": "APT"}, "to": [{"email": user.email}], "subject": email_subject(event), "htmlContent": email_html(event)}`, `aiohttp.ClientTimeout(total=30)`. Non-2xx → raise `RuntimeError` with status + body snippet (notifier releases claim → retry next cycle).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_email_channel.py`:

```python
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apt.domain.events import MatchEvent
from apt.domain.models import Alert, AlertFilters, Listing, User
from apt.notify.email_channel import BREVO_URL, EmailChannel

USER = User(id=1, google_sub="g", email="user@example.com")


def make_event():
    listing = Listing(source="yad2", source_id="a1", url="https://e.com/a1", city="חיפה", price=5000)
    alert = Alert(id=1, user_id=1, name="x", filters=AlertFilters(), channels=["email"])
    return MatchEvent(kind="new", listing=listing, alert=alert)


def make_session(status=201, body="created"):
    response = MagicMock()
    response.status = status
    response.text = AsyncMock(return_value=body)
    request_ctx = MagicMock()
    request_ctx.__aenter__ = AsyncMock(return_value=response)
    request_ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post = MagicMock(return_value=request_ctx)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    return session_ctx, session


def test_applicable():
    channel = EmailChannel("key", "apt@example.com")
    assert channel.applicable(USER) is True
    assert channel.applicable(User(id=2, google_sub="h", email="")) is False


async def test_deliver_posts_to_brevo():
    session_ctx, session = make_session()
    with patch("apt.notify.email_channel.aiohttp.ClientSession", return_value=session_ctx):
        await EmailChannel("key-1", "apt@example.com").deliver(USER, make_event())
    args, kwargs = session.post.call_args
    assert args[0] == BREVO_URL
    payload = kwargs["json"]
    assert payload["to"] == [{"email": "user@example.com"}]
    assert payload["sender"]["email"] == "apt@example.com"
    assert "חיפה" in payload["subject"]
    assert 'dir="rtl"' in payload["htmlContent"]


async def test_deliver_raises_on_error_status():
    session_ctx, session = make_session(status=401, body="bad key")
    with patch("apt.notify.email_channel.aiohttp.ClientSession", return_value=session_ctx):
        with pytest.raises(RuntimeError, match="401"):
            await EmailChannel("key-1", "apt@example.com").deliver(USER, make_event())
```

- [ ] **Step 2: Run to verify failure** — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`backend/apt/notify/email_channel.py`:

```python
import aiohttp

from apt.domain.events import MatchEvent
from apt.domain.models import User
from apt.notify.format import email_html, email_subject

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
REQUEST_TIMEOUT_SECONDS = 30


class EmailChannel:
    name = "email"

    def __init__(self, api_key: str, from_email: str):
        self._api_key = api_key
        self._from_email = from_email

    def applicable(self, user: User) -> bool:
        return bool(user.email)

    async def deliver(self, user: User, event: MatchEvent) -> None:
        payload = {
            "sender": {"email": self._from_email, "name": "APT"},
            "to": [{"email": user.email}],
            "subject": email_subject(event),
            "htmlContent": email_html(event),
        }
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(BREVO_URL, json=payload, headers={"api-key": self._api_key}) as response:
                if response.status >= 300:
                    body = (await response.text())[:200]
                    raise RuntimeError(f"brevo returned {response.status}: {body}")
```

- [ ] **Step 4: Run to verify pass, then full suite; commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/notify/email_channel.py backend/tests/test_email_channel.py
git commit -m "feat: add brevo email delivery channel"
```

---

### Task 6: Telegram bot handlers

**Files:**
- Create: `backend/apt/bot.py`
- Test: `backend/tests/test_bot.py`

**Interfaces:**
- Consumes: `LinkTokenRepo` (Task 1), `UserRepo`, `AlertRepo`, `ListingRepo.search`, `telegram_message` formatting style (compact variant inline).
- Produces (`apt.bot`):
  - `build_application(token: str, conn, site_url: str, now_fn=None) -> telegram.ext.Application` — registers all handlers below (used by `bot_main`, Task 7).
  - Handler functions (each takes `(update, context)` and reads `conn`, `site_url`, `now_fn` from `context.bot_data`):
    - `start`: with a deep-link arg (`/start <token>`) → `LinkTokenRepo.consume`; success → `UserRepo.set_telegram_chat(user_id, chat_id)` + Hebrew confirmation ("החשבון קושר בהצלחה!"); invalid/expired → Hebrew error pointing back to the site. Without args → Hebrew welcome with command list + site link.
    - `help_command`: same welcome text.
    - `matches`: unlinked chat → Hebrew "link first" message with site link. Linked → for each of the user's ACTIVE alerts, `ListingRepo.search(alert.filters, limit=3)`; reply one Hebrew HTML message per alert (name + up to 3 compact listing lines: price, location, link); no alerts → prompt to create one on the site.
    - `pause` / `resume`: unlinked → link-first message; linked → `AlertRepo.set_active(alert.id, False/True)` on ALL the user's alerts + Hebrew confirmation with count.
  - All bot replies `parse_mode="HTML"`; user content escaped via `html.escape`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_bot.py`:

```python
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from apt.bot import help_command, matches, pause, resume, start
from apt.domain.models import AlertFilters, Listing, Location
from apt.repo.alerts import AlertRepo
from apt.repo.link_tokens import LinkTokenRepo
from apt.repo.listings import ListingRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
SITE = "https://apt.example.com"


def make_update(chat_id=42, args=None):
    message = SimpleNamespace(chat_id=chat_id, reply_text=AsyncMock())
    update = SimpleNamespace(effective_message=message, effective_chat=SimpleNamespace(id=chat_id))
    context = SimpleNamespace(
        args=args or [],
        bot_data={"conn": None, "site_url": SITE, "now_fn": lambda: NOW},
    )
    return update, context


def reply_text(update):
    return update.effective_message.reply_text.call_args.args[0]


def make_user(conn, chat_id=None):
    user = UserRepo(conn).upsert_google_user("g-1", "a@b.com", NOW)
    if chat_id is not None:
        UserRepo(conn).set_telegram_chat(user.id, chat_id)
    return UserRepo(conn).get(user.id)


async def test_start_without_token_shows_welcome(conn):
    update, context = make_update()
    context.bot_data["conn"] = conn
    await start(update, context)
    assert SITE in reply_text(update)


async def test_start_with_valid_token_links_account(conn):
    user = make_user(conn)
    LinkTokenRepo(conn).create("tok-1", user.id, NOW)
    update, context = make_update(chat_id=42, args=["tok-1"])
    context.bot_data["conn"] = conn
    await start(update, context)
    assert UserRepo(conn).get(user.id).telegram_chat_id == 42
    assert "בהצלחה" in reply_text(update)


async def test_start_with_bad_token_shows_error(conn):
    update, context = make_update(args=["nope"])
    context.bot_data["conn"] = conn
    await start(update, context)
    assert UserRepo(conn).get_by_telegram_chat(42) is None
    assert SITE in reply_text(update)


async def test_matches_unlinked_prompts_linking(conn):
    update, context = make_update()
    context.bot_data["conn"] = conn
    await matches(update, context)
    assert SITE in reply_text(update)


async def test_matches_lists_listings_per_alert(conn):
    user = make_user(conn, chat_id=42)
    AlertRepo(conn).create(user.id, "חיפה עד 6000",
                           AlertFilters(locations=[Location(city="חיפה")], max_price=6000),
                           ["telegram"], NOW)
    ListingRepo(conn).upsert(
        Listing(source="yad2", source_id="a1", url="https://e.com/a1", city="חיפה", price=5000), NOW)
    update, context = make_update(chat_id=42)
    context.bot_data["conn"] = conn
    await matches(update, context)
    text = reply_text(update)
    assert "חיפה עד 6000" in text
    assert "₪5,000" in text


async def test_pause_and_resume_toggle_all_alerts(conn):
    user = make_user(conn, chat_id=42)
    repo = AlertRepo(conn)
    alert = repo.create(user.id, "x", AlertFilters(), ["telegram"], NOW)
    update, context = make_update(chat_id=42)
    context.bot_data["conn"] = conn
    await pause(update, context)
    assert repo.get(alert.id).active is False
    await resume(update, context)
    assert repo.get(alert.id).active is True


async def test_help_shows_commands(conn):
    update, context = make_update()
    context.bot_data["conn"] = conn
    await help_command(update, context)
    text = reply_text(update)
    assert "/matches" in text
```

- [ ] **Step 2: Run to verify failure** — `ModuleNotFoundError: apt.bot`.

- [ ] **Step 3: Implement**

`backend/apt/bot.py`:

```python
import html
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Callable

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from apt.repo.alerts import AlertRepo
from apt.repo.link_tokens import LinkTokenRepo
from apt.repo.listings import ListingRepo
from apt.repo.users import UserRepo

logger = logging.getLogger(__name__)

WELCOME = (
    "🏠 <b>APT - חיפוש דירות להשכרה</b>\n"
    "הבוט שולח התראות על דירות חדשות שמתאימות לחיפושים שלך.\n\n"
    "פקודות:\n"
    "/matches - הדירות האחרונות שמתאימות לחיפושים שלך\n"
    "/pause - השהיית כל ההתראות\n"
    "/resume - חידוש ההתראות\n"
    "/help - ההודעה הזאת\n\n"
    'יצירת חיפושים ועריכתם באתר: <a href="{site}">{site}</a>'
)
LINK_FIRST = (
    'כדי להשתמש בבוט צריך קודם לקשר את החשבון מהאתר: <a href="{site}">{site}</a>'
)


def _tools(context: ContextTypes.DEFAULT_TYPE):
    data = context.bot_data
    now_fn = data.get("now_fn") or (lambda: datetime.now(timezone.utc))
    return data["conn"], data["site_url"], now_fn


async def _reply(update: Update, text: str) -> None:
    await update.effective_message.reply_text(text, parse_mode="HTML")


def _linked_user(conn: sqlite3.Connection, update: Update):
    return UserRepo(conn).get_by_telegram_chat(update.effective_message.chat_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn, site_url, now_fn = _tools(context)
    if context.args:
        user_id = LinkTokenRepo(conn).consume(context.args[0], now_fn())
        if user_id is not None:
            UserRepo(conn).set_telegram_chat(user_id, update.effective_message.chat_id)
            await _reply(update, "✅ החשבון קושר בהצלחה! מעכשיו תקבלו כאן התראות על דירות חדשות.")
            return
        await _reply(update, "הקישור פג תוקף או שגוי. " + LINK_FIRST.format(site=site_url))
        return
    await _reply(update, WELCOME.format(site=site_url))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _, site_url, _ = _tools(context)
    await _reply(update, WELCOME.format(site=site_url))


def _listing_line(listing) -> str:
    price = f"₪{listing.price:,}" if listing.price is not None else "מחיר לא ידוע"
    parts = [part for part in (listing.street, listing.neighborhood, listing.city) if part]
    location = html.escape(", ".join(dict.fromkeys(parts)), quote=False)
    url = html.escape(listing.url, quote=True)
    return f'• {price} - {location} - <a href="{url}">למודעה</a>'


async def matches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn, site_url, _ = _tools(context)
    user = _linked_user(conn, update)
    if user is None:
        await _reply(update, LINK_FIRST.format(site=site_url))
        return
    alerts = [alert for alert in AlertRepo(conn).list_for_user(user.id) if alert.active]
    if not alerts:
        await _reply(update, f'אין לך עדיין חיפושים. אפשר ליצור באתר: <a href="{site_url}">{site_url}</a>')
        return
    listings_repo = ListingRepo(conn)
    for alert in alerts:
        found = listings_repo.search(alert.filters, limit=3)
        name = html.escape(alert.name, quote=False)
        if found:
            lines = "\n".join(_listing_line(listing) for listing in found)
            await _reply(update, f"<b>{name}</b>\n{lines}")
        else:
            await _reply(update, f"<b>{name}</b>\nאין עדיין דירות מתאימות.")


async def _set_all_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE, active: bool) -> None:
    conn, site_url, _ = _tools(context)
    user = _linked_user(conn, update)
    if user is None:
        await _reply(update, LINK_FIRST.format(site=site_url))
        return
    repo = AlertRepo(conn)
    alerts = repo.list_for_user(user.id)
    for alert in alerts:
        repo.set_active(alert.id, active)
    verb = "חודשו" if active else "הושהו"
    await _reply(update, f"{len(alerts)} חיפושים {verb}.")


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_all_alerts(update, context, False)


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_all_alerts(update, context, True)


def build_application(
    token: str,
    conn: sqlite3.Connection,
    site_url: str,
    now_fn: Callable[[], datetime] | None = None,
) -> Application:
    application = Application.builder().token(token).build()
    application.bot_data.update({"conn": conn, "site_url": site_url, "now_fn": now_fn})
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("matches", matches))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))
    return application
```

- [ ] **Step 4: Run to verify pass, then full suite; commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/bot.py backend/tests/test_bot.py
git commit -m "feat: add telegram bot handlers"
```

---

### Task 7: Bot entrypoint + scraper wiring + docs

**Files:**
- Create: `backend/apt/bot_main.py`
- Modify: `backend/apt/scraper_main.py` (use ChannelNotifier when configured)
- Modify: `backend/README.md`
- Test: `backend/tests/test_entrypoint_wiring.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `apt.bot_main`: `python -m apt.bot_main` — env `TELEGRAM_BOT_TOKEN` (required), `APT_DB_PATH` (default `data/apt.db`), `APT_SITE_URL` (default `https://apt.example.com` until plan 6 assigns the real domain); connects+migrates, `build_application(...).run_polling()`. Missing token → clear error exit.
  - `apt.scraper_main.build_notifier(conn) -> Notifier`: reads env — when `TELEGRAM_BOT_TOKEN` set, includes `TelegramChannel(conn, telegram.Bot(token))`; when `BREVO_API_KEY` AND `APT_EMAIL_FROM` set, includes `EmailChannel(...)`; any channel configured → `ChannelNotifier(conn, channels)`; none → `LogNotifier()` (dev mode). `main()` calls `build_notifier` instead of hardcoding LogNotifier.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_entrypoint_wiring.py`:

```python
from apt import bot_main, scraper_main
from apt.notify.base import LogNotifier
from apt.notify.notifier import ChannelNotifier
from apt.repo.db import connect, migrate


def make_conn(tmp_path):
    conn = connect(tmp_path / "wiring.db")
    migrate(conn)
    return conn


def test_build_notifier_defaults_to_log(monkeypatch, tmp_path):
    for var in ("TELEGRAM_BOT_TOKEN", "BREVO_API_KEY", "APT_EMAIL_FROM"):
        monkeypatch.delenv(var, raising=False)
    assert isinstance(scraper_main.build_notifier(make_conn(tmp_path)), LogNotifier)


def test_build_notifier_with_telegram(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    notifier = scraper_main.build_notifier(make_conn(tmp_path))
    assert isinstance(notifier, ChannelNotifier)
    assert set(notifier._channels) == {"telegram"}


def test_build_notifier_with_both_channels(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("APT_EMAIL_FROM", "apt@example.com")
    notifier = scraper_main.build_notifier(make_conn(tmp_path))
    assert set(notifier._channels) == {"telegram", "email"}


def test_bot_config_requires_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("APT_DB_PATH", "/tmp/x.db")
    try:
        bot_main.load_config()
        raised = False
    except SystemExit:
        raised = True
    assert raised


def test_bot_config_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("APT_DB_PATH", "/tmp/x.db")
    monkeypatch.setenv("APT_SITE_URL", "https://apt.co.il")
    config = bot_main.load_config()
    assert config.token == "123:abc"
    assert config.site_url == "https://apt.co.il"
```

- [ ] **Step 2: Run to verify failure** — `ImportError` / `AttributeError`.

- [ ] **Step 3: Implement**

`backend/apt/bot_main.py`:

```python
import logging
import os
import sys
from pathlib import Path

from pydantic import BaseModel

from apt.bot import build_application
from apt.repo.db import connect, migrate

logger = logging.getLogger(__name__)


class BotConfig(BaseModel):
    token: str
    db_path: Path
    site_url: str


def load_config() -> BotConfig:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set")
        sys.exit(1)
    return BotConfig(
        token=token,
        db_path=Path(os.getenv("APT_DB_PATH", "data/apt.db")),
        site_url=os.getenv("APT_SITE_URL", "https://apt.example.com"),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config = load_config()
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(config.db_path)
    migrate(conn)
    application = build_application(config.token, conn, config.site_url)
    logger.info("bot starting (db=%s)", config.db_path)
    application.run_polling()


if __name__ == "__main__":
    main()
```

In `backend/apt/scraper_main.py`: add imports (`telegram.Bot`, `ChannelNotifier`, `TelegramChannel`, `EmailChannel`, `sqlite3`) and the factory, and use it in `main()`:

```python
def build_notifier(conn: sqlite3.Connection):
    channels: dict = {}
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if token:
        channels["telegram"] = TelegramChannel(conn, Bot(token))
    api_key = os.getenv("BREVO_API_KEY", "")
    from_email = os.getenv("APT_EMAIL_FROM", "")
    if api_key and from_email:
        channels["email"] = EmailChannel(api_key, from_email)
    if channels:
        return ChannelNotifier(conn, channels)
    return LogNotifier()
```

and replace `notifier = LogNotifier()` with `notifier = build_notifier(conn)`.

- [ ] **Step 4: Update backend/README.md**

In the Layout section, replace the `apt/notify/` line with:

```markdown
- `apt/notify/` — delivery: formatting, `ChannelNotifier` (exactly-once), Telegram + Brevo email channels
- `apt/bot.py` / `apt/bot_main.py` — Telegram bot (linking, /matches, /pause, /resume)
```

Append after the "Running the scraper" section:

```markdown
## Running the bot

```bash
TELEGRAM_BOT_TOKEN=123:abc APT_DB_PATH=data/apt.db APT_SITE_URL=https://apt.example.com python -m apt.bot_main
```

The scraper delivers real notifications when `TELEGRAM_BOT_TOKEN` (Telegram) and/or
`BREVO_API_KEY` + `APT_EMAIL_FROM` (email) are set; otherwise it logs matches only.
```

- [ ] **Step 5: Run full suite; commit**

`pytest` — everything green.

```bash
cd /Users/alon.i/APT
git add backend/apt/bot_main.py backend/apt/scraper_main.py backend/README.md backend/tests/test_entrypoint_wiring.py
git commit -m "feat: add bot entrypoint and wire real notifier into scraper"
```

---

## Plan 3 Exit Criteria

- Full suite green (~125 tests).
- `ChannelNotifier` satisfies plan 2's `Notifier` protocol and never raises; exactly-once enforced at (alert, listing, channel, kind, price_key).
- Bot links accounts via tokens plan 4's API will mint (`LinkTokenRepo.create`), and serves /matches, /pause, /resume in Hebrew.
- Two runnable services: `python -m apt.scraper_main` (with real channels when env is set) and `python -m apt.bot_main`.
