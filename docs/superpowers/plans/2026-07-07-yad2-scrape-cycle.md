# APT Plan 2/6: Yad2 Source + Scrape Cycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the scraping half of APT: a generalized Yad2 source (any mapped Israeli city, not hardcoded Krayot), and the scrape-cycle orchestrator that fetches listings, stores them, detects new/price-dropped listings, matches them against active alerts, and hands match events to a notifier.

**Architecture:** New subpackages in the existing `apt` package: `apt.sources` (Source protocol + Yad2 implementation split into pure parsing vs. HTTP client), `apt.notify` (Notifier protocol + LogNotifier placeholder until plan 3), `apt.cycle` (orchestrator), `apt.scraper_main` (service entrypoint). Everything builds on plan 1's repositories. HTTP behavior is reference-proven: the endpoints, headers, and JSON paths come verbatim from `docs/superpowers/specs/2026-07-07-yad2-reference-notes.md` ("**the notes file**" below — implementers treat it as ground truth).

**Tech Stack:** Python 3.12, aiohttp, BeautifulSoup4, Pydantic v2; tests with pytest + pytest-asyncio + aioresponses (HTTP mocking).

## Global Constraints

- All of plan 1's constraints still hold (WAL, `now` always a parameter — timezone-aware UTC, ISO strings, no ORM, exact source/channel strings).
- New runtime deps: `aiohttp>=3.9`, `beautifulsoup4>=4.12`. New dev deps: `aioresponses>=0.7`, `pytest-asyncio>=0.23` with `asyncio_mode = "auto"`.
- **Critical repo contract from plan 1's final review:** `ListingRepo.upsert` is last-scrape-wins on every field. The cycle must merge-preserve enrichment-only fields (description, has_mamad/has_elevator, entry_date) before re-upserting feed-level listings (Task 6's `merge_preserving_enrichment`).
- Politeness (design D11): randomized 2.0–8.0s delay between successive feed-page requests; retry only on HTTP 500/502/503/504, 3 attempts, `2**attempt` backoff; `aiohttp.ClientTimeout(total=30)` actually passed to the session (the reference constructed it but never used it — fix, don't copy, that bug).
- Yad2 exact values (URL templates, `DEFAULT_HEADERS`, `USER_AGENT`, JSON key paths, `normalize_text` semantics incl. the קריית→קרית replacement) come **verbatim from the notes file** — never retype them from memory.
- Tag-derived amenities are `True` when the tag is present and `None` (unknown) when absent — never `False` from tags alone; only detail enrichment (`inProperty.includeSecurityRoom`/`includeElevator`, checked with `in`) may set `False`.
- Max 10 feed pages per Yad2 query (`MAX_PAGES_PER_QUERY = 10`); log when truncating.
- Work from `/Users/alon.i/APT/backend` with `.venv` activated; commits from `/Users/alon.i/APT`; no Co-Authored-By lines.

---

### Task 1: Protocols, match events, and new dependencies

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/apt/sources/__init__.py` (empty)
- Create: `backend/apt/sources/base.py`
- Create: `backend/apt/notify/__init__.py` (empty)
- Create: `backend/apt/notify/base.py`
- Create: `backend/apt/domain/events.py`
- Test: `backend/tests/test_events_and_notify.py`

**Interfaces:**
- Consumes: `Listing`, `Alert`, `Location` from `apt.domain.models` (plan 1).
- Produces:
  - `apt.domain.events.MatchEvent(kind: Literal["new","price_drop"], listing: Listing, alert: Alert, old_price: int | None = None)`
  - `apt.sources.base.SourceError(Exception)`; `apt.sources.base.Source` (Protocol): attribute `name: str`, `async fetch(locations: list[Location]) -> list[Listing]`, `async enrich(listing: Listing) -> Listing`
  - `apt.notify.base.Notifier` (Protocol): `async send(event: MatchEvent) -> None`; `apt.notify.base.LogNotifier` — records events on `.sent` and logs (real channels arrive in plan 3).

- [ ] **Step 1: Update pyproject.toml**

In `backend/pyproject.toml`, change the `dependencies` and dev lists and pytest options to:

```toml
dependencies = [
    "pydantic>=2.7",
    "aiohttp>=3.9",
    "beautifulsoup4>=4.12",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "aioresponses>=0.7",
]
```

and extend the pytest section to:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

Then: `cd /Users/alon.i/APT/backend && source .venv/bin/activate && uv pip install -e '.[dev]'` and `pytest` — expect all 60 existing tests still passing.

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_events_and_notify.py`:

```python
import pytest
from pydantic import ValidationError

from apt.domain.events import MatchEvent
from apt.domain.models import Alert, AlertFilters, Listing
from apt.notify.base import LogNotifier


def make_listing():
    return Listing(source="yad2", source_id="x1", url="https://e.com/x1", city="חיפה")


def make_alert():
    return Alert(id=1, user_id=1, name="a", filters=AlertFilters(), channels=["telegram"])


def test_match_event_kinds():
    event = MatchEvent(kind="new", listing=make_listing(), alert=make_alert())
    assert event.old_price is None
    drop = MatchEvent(kind="price_drop", listing=make_listing(), alert=make_alert(), old_price=6000)
    assert drop.old_price == 6000
    with pytest.raises(ValidationError):
        MatchEvent(kind="price_rise", listing=make_listing(), alert=make_alert())


async def test_log_notifier_records_events():
    notifier = LogNotifier()
    event = MatchEvent(kind="new", listing=make_listing(), alert=make_alert())
    await notifier.send(event)
    assert notifier.sent == [event]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_events_and_notify.py -v` — expected FAIL with `ModuleNotFoundError: No module named 'apt.domain.events'`.

- [ ] **Step 4: Implement**

`backend/apt/domain/events.py`:

```python
from typing import Literal

from pydantic import BaseModel

from apt.domain.models import Alert, Listing


class MatchEvent(BaseModel):
    kind: Literal["new", "price_drop"]
    listing: Listing
    alert: Alert
    old_price: int | None = None
```

`backend/apt/sources/base.py`:

```python
from typing import Protocol

from apt.domain.models import Listing, Location


class SourceError(Exception):
    """A source failed to fetch; the cycle records it and moves on."""


class Source(Protocol):
    name: str

    async def fetch(self, locations: list[Location]) -> list[Listing]: ...

    async def enrich(self, listing: Listing) -> Listing: ...
```

`backend/apt/notify/base.py`:

```python
import logging
from typing import Protocol

from apt.domain.events import MatchEvent


class Notifier(Protocol):
    async def send(self, event: MatchEvent) -> None: ...


class LogNotifier:
    """Records and logs match events until real channels land (plan 3)."""

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self.sent: list[MatchEvent] = []

    async def send(self, event: MatchEvent) -> None:
        self.sent.append(event)
        self._logger.info(
            "match %s: alert %s listing %s", event.kind, event.alert.id, event.listing.id
        )
```

Create empty `backend/apt/sources/__init__.py` and `backend/apt/notify/__init__.py`.

- [ ] **Step 5: Run tests to verify they pass, then run the whole suite**

Run: `pytest tests/test_events_and_notify.py -v` — all PASS. Then `pytest` — 62 passed.

- [ ] **Step 6: Commit**

```bash
cd /Users/alon.i/APT
git add backend/pyproject.toml backend/apt/sources/ backend/apt/notify/ backend/apt/domain/events.py backend/tests/test_events_and_notify.py
git commit -m "feat: add source/notifier protocols, match events, scraping deps"
```

---

### Task 2: Yad2 location registry

**Files:**
- Create: `backend/apt/sources/yad2_locations.py`
- Test: `backend/tests/test_yad2_locations.py`

**Interfaces:**
- Consumes: `Location` from plan 1.
- Produces (`apt.sources.yad2_locations`):
  - `normalize_text(value: str | None) -> str` — verbatim reference semantics (notes file §6): strip all whitespace, casefold, replace `קריית` with `קרית`.
  - `Yad2Query(city_id: int, area_id: int, route_slug: str)` — frozen (hashable) Pydantic model.
  - `KNOWN_CITIES: dict[str, Yad2Query]` — seeded verbatim from the notes file §7 `KNOWN_CITIES` (5 cities). Extending coverage = adding entries here.
  - `resolve(location: Location) -> Yad2Query | None` — by normalized city name; unknown city → None.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_yad2_locations.py`:

```python
from apt.domain.models import Location
from apt.sources.yad2_locations import KNOWN_CITIES, Yad2Query, normalize_text, resolve


def test_normalize_text_whitespace_case_and_kiryat():
    assert normalize_text("  תל  אביב ") == "תלאביב"
    assert normalize_text("קריית ים") == normalize_text("קרית ים")
    assert normalize_text(None) == ""


def test_resolve_known_city():
    query = resolve(Location(city="חיפה"))
    assert query == Yad2Query(city_id=4000, area_id=5, route_slug="coastal-north")


def test_resolve_tolerates_spelling_variant():
    assert resolve(Location(city="קרית ים")) == KNOWN_CITIES["קריית ים"]


def test_resolve_unknown_city_returns_none():
    assert resolve(Location(city="עיר לא קיימת")) is None


def test_yad2_query_is_hashable():
    assert len({resolve(Location(city="חיפה")), resolve(Location(city="חיפה"))}) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_yad2_locations.py -v` — FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`backend/apt/sources/yad2_locations.py`:

```python
from pydantic import BaseModel, ConfigDict

from apt.domain.models import Location


def normalize_text(value: str | None) -> str:
    value = (value or "").replace("קריית", "קרית")
    return "".join(value.split()).casefold()


class Yad2Query(BaseModel):
    model_config = ConfigDict(frozen=True)

    city_id: int
    area_id: int
    route_slug: str


# Seeded from the predecessor project (see yad2-reference-notes §7);
# supporting a new city = adding its Yad2 ids here.
KNOWN_CITIES: dict[str, Yad2Query] = {
    "תל אביב": Yad2Query(city_id=5000, area_id=1, route_slug="tel-aviv-area"),
    "חיפה": Yad2Query(city_id=4000, area_id=5, route_slug="coastal-north"),
    "קריית ים": Yad2Query(city_id=9600, area_id=6, route_slug="coastal-north"),
    "קריית מוצקין": Yad2Query(city_id=8200, area_id=6, route_slug="coastal-north"),
    "קריית ביאליק": Yad2Query(city_id=9500, area_id=6, route_slug="coastal-north"),
}

_BY_NORMALIZED = {normalize_text(name): query for name, query in KNOWN_CITIES.items()}


def resolve(location: Location) -> Yad2Query | None:
    return _BY_NORMALIZED.get(normalize_text(location.city))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_yad2_locations.py -v` — all PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/sources/yad2_locations.py backend/tests/test_yad2_locations.py
git commit -m "feat: add yad2 city registry and name normalization"
```

---

### Task 3: Yad2 feed parsing (pure)

**Files:**
- Create: `backend/tests/fixtures/yad2_feed.json` — copy the feed fixture JSON **verbatim** from the notes file section "Minimal Synthetic Fixture" (the first JSON block).
- Create: `backend/apt/sources/yad2_parse.py`
- Test: `backend/tests/test_yad2_parse.py`

**Interfaces:**
- Consumes: `Listing` from plan 1; JSON key paths from the notes file §3–4.
- Produces (`apt.sources.yad2_parse`):
  - `extract_query_data(response_json: dict, sentinel: str) -> dict` — navigates `pageProps → dehydratedState → queries[queryKey[0]==sentinel] → state.data`; `{}` on any mismatch.
  - `extract_feed(response_json: dict) -> dict` — sentinel `"realestate-rent-feed"`.
  - `total_pages(feed_data: dict) -> int` — from `pagination.totalPages`, default 1.
  - `parse_feed_items(feed_data: dict) -> list[Listing]` — iterates all list-valued buckets except `pagination`/`lookalike`, dedupes by token.
  - `parse_item(item: dict) -> Listing | None` — None when token or city missing. Field mapping per notes §4; floor via isdigit (negative/blank → None); tags→names; mamad/elevator True-or-None from tags; token coerced to str.

- [ ] **Step 1: Create the fixture**

Copy the first JSON block from the notes file's "Minimal Synthetic Fixture" section into `backend/tests/fixtures/yad2_feed.json`, byte-for-byte.

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_yad2_parse.py`:

```python
import json
from pathlib import Path

from apt.sources.yad2_parse import (extract_feed, parse_feed_items, parse_item,
                                    total_pages)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "yad2_feed.json").read_text(encoding="utf-8")
)


def feed():
    return extract_feed(FIXTURE)


def by_token(listings):
    return {listing.source_id: listing for listing in listings}


def test_extract_feed_finds_data_and_handles_garbage():
    assert "pagination" in feed()
    assert extract_feed({}) == {}
    assert extract_feed({"pageProps": {"dehydratedState": {"queries": [{"queryKey": ["other"]}]}}}) == {}


def test_total_pages():
    assert total_pages(feed()) == 2
    assert total_pages({}) == 1


def test_parse_feed_items_skips_lookalike_and_dedupes():
    listings = parse_feed_items(feed())
    tokens = {listing.source_id for listing in listings}
    assert tokens == {"abc123", "def456", "promo999"}


def test_parse_item_full_fields():
    listing = by_token(parse_feed_items(feed()))["abc123"]
    assert listing.source == "yad2"
    assert listing.url == "https://www.yad2.co.il/realestate/item/abc123"
    assert listing.city == "קריית ים"
    assert listing.neighborhood is None
    assert listing.street == "הרצל"
    assert listing.price == 4500
    assert listing.rooms == 3.5
    assert listing.size_sqm == 80
    assert listing.floor == 3
    assert listing.has_elevator is True
    assert listing.has_mamad is None
    assert listing.tags == ["מעלית", "חניה"]
    assert listing.photo_urls == ["https://img.yad2.co.il/Pics/abc123/1.jpg"]


def test_parse_item_mamad_and_ground_floor():
    listing = by_token(parse_feed_items(feed()))["def456"]
    assert listing.has_mamad is True
    assert listing.floor == 0
    assert listing.neighborhood == "קריית חיים מערבית"


def test_parse_item_nulls_become_none():
    listing = by_token(parse_feed_items(feed()))["promo999"]
    assert listing.price == 3800
    assert listing.rooms is None
    assert listing.size_sqm is None
    assert listing.floor is None
    assert listing.has_mamad is None
    assert listing.has_elevator is None
    assert listing.street is None


def test_parse_item_missing_token_or_city():
    assert parse_item({"price": 1}) is None
    assert parse_item({"token": "t", "address": {}}) is None


def test_parse_item_int_token_coerced():
    listing = parse_item({"token": 777, "address": {"city": {"text": "חיפה"}}})
    assert listing.source_id == "777"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_yad2_parse.py -v` — FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

`backend/apt/sources/yad2_parse.py`:

```python
"""Pure parsing of Yad2 Next.js data payloads (see yad2-reference-notes §3-5).

Tag-derived amenities are True when the tag is present and None (unknown)
when absent; only detail enrichment may set an explicit False.
"""

from typing import Any

from apt.domain.models import Listing

SKIPPED_BUCKETS = {"pagination", "lookalike"}
APARTMENT_PAGE_URL = "https://www.yad2.co.il/realestate/item/{token}"


def extract_query_data(response_json: dict[str, Any], sentinel: str) -> dict[str, Any]:
    queries = (
        response_json.get("pageProps", {}).get("dehydratedState", {}).get("queries", [])
    )
    for query in queries:
        key = query.get("queryKey") or []
        if key and key[0] == sentinel:
            return query.get("state", {}).get("data", {}) or {}
    return {}


def extract_feed(response_json: dict[str, Any]) -> dict[str, Any]:
    return extract_query_data(response_json, "realestate-rent-feed")


def total_pages(feed_data: dict[str, Any]) -> int:
    return int((feed_data.get("pagination") or {}).get("totalPages") or 1)


def _text(node: dict[str, Any] | None) -> str | None:
    return ((node or {}).get("text") or "") or None


def _parse_floor(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value)
    return int(text) if text.isdigit() else None


def parse_item(item: dict[str, Any]) -> Listing | None:
    token = item.get("token")
    if not token:
        return None
    address = item.get("address") or {}
    city = _text(address.get("city"))
    if city is None:
        return None
    details = item.get("additionalDetails") or {}
    tags = [tag.get("name") for tag in item.get("tags") or [] if tag.get("name")]
    tag_text = " ".join(tags)
    price = item.get("price")
    rooms = details.get("roomsCount")
    size = details.get("squareMeter")
    token = str(token)
    return Listing(
        source="yad2",
        source_id=token,
        url=APARTMENT_PAGE_URL.format(token=token),
        city=city,
        neighborhood=_text(address.get("neighborhood")),
        street=_text(address.get("street")),
        price=int(price) if price is not None else None,
        rooms=float(rooms) if rooms is not None else None,
        size_sqm=int(size) if size is not None else None,
        floor=_parse_floor((address.get("house") or {}).get("floor")),
        has_mamad=True if ('ממ"ד' in tag_text or "ממד" in tag_text) else None,
        has_elevator=True if "מעלית" in tag_text else None,
        tags=tags,
        photo_urls=[str(url) for url in (item.get("metaData") or {}).get("images") or []],
    )


def parse_feed_items(feed_data: dict[str, Any]) -> list[Listing]:
    listings: list[Listing] = []
    seen: set[str] = set()
    for bucket, items in feed_data.items():
        if bucket in SKIPPED_BUCKETS or not isinstance(items, list):
            continue
        for item in items:
            listing = parse_item(item)
            if listing is not None and listing.source_id not in seen:
                seen.add(listing.source_id)
                listings.append(listing)
    return listings
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_yad2_parse.py -v` — all PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/sources/yad2_parse.py backend/tests/fixtures/yad2_feed.json backend/tests/test_yad2_parse.py
git commit -m "feat: add yad2 feed parsing"
```

---

### Task 4: Yad2 detail parsing and enrichment application (pure)

**Files:**
- Create: `backend/tests/fixtures/yad2_item_detail.json` — copy the second JSON block ("Corresponding detail response fixture") from the notes file, verbatim.
- Modify: `backend/apt/sources/yad2_parse.py` (append two functions)
- Test: `backend/tests/test_yad2_detail.py`

**Interfaces:**
- Consumes: Task 3's `extract_query_data`; notes file §5 semantics.
- Produces (appended to `apt.sources.yad2_parse`):
  - `extract_item_detail(response_json: dict) -> dict` — sentinel `"item"`.
  - `apply_item_detail(listing: Listing, detail: dict) -> Listing` — returns an updated copy: `inProperty.includeSecurityRoom`/`includeElevator` applied via `in`-membership (explicit False is applied; missing key leaves the tag value), truthy `metaData.description`, non-None `additionalDetails.squareMeter`/`roomsCount` override.

- [ ] **Step 1: Create the fixture and write the failing tests**

`backend/tests/test_yad2_detail.py`:

```python
import json
from pathlib import Path

from apt.domain.models import Listing
from apt.sources.yad2_parse import apply_item_detail, extract_item_detail

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "yad2_item_detail.json").read_text(encoding="utf-8")
)


def make_listing(**overrides):
    base = dict(source="yad2", source_id="abc123", url="https://e.com/abc123",
                city="חיפה", has_elevator=True, size_sqm=80, rooms=3.0)
    base.update(overrides)
    return Listing(**base)


def test_extract_item_detail():
    detail = extract_item_detail(FIXTURE)
    assert detail["inProperty"]["includeSecurityRoom"] is True
    assert extract_item_detail({}) == {}


def test_apply_detail_overrides_and_explicit_false():
    enriched = apply_item_detail(make_listing(), extract_item_detail(FIXTURE))
    assert enriched.has_mamad is True
    assert enriched.has_elevator is False
    assert enriched.description == "דירה מרווחת עם נוף לים"
    assert enriched.size_sqm == 85
    assert enriched.rooms == 3.5


def test_apply_detail_missing_keys_leave_listing_untouched():
    original = make_listing()
    enriched = apply_item_detail(original, {})
    assert enriched == original


def test_apply_detail_partial_keeps_feed_values():
    detail = {"inProperty": {}, "metaData": {"description": ""}, "additionalDetails": {"squareMeter": None}}
    enriched = apply_item_detail(make_listing(), detail)
    assert enriched.has_elevator is True
    assert enriched.description == ""
    assert enriched.size_sqm == 80
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_yad2_detail.py -v` — FAIL with `ImportError` (functions don't exist yet).

- [ ] **Step 3: Implement (append to `yad2_parse.py`)**

```python
def extract_item_detail(response_json: dict[str, Any]) -> dict[str, Any]:
    return extract_query_data(response_json, "item")


def apply_item_detail(listing: Listing, detail: dict[str, Any]) -> Listing:
    updates: dict[str, Any] = {}
    in_property = detail.get("inProperty") or {}
    # 'in' membership: an explicit False is authoritative, a missing key is not.
    if "includeSecurityRoom" in in_property:
        updates["has_mamad"] = bool(in_property["includeSecurityRoom"])
    if "includeElevator" in in_property:
        updates["has_elevator"] = bool(in_property["includeElevator"])
    description = (detail.get("metaData") or {}).get("description")
    if description:
        updates["description"] = description
    details = detail.get("additionalDetails") or {}
    if details.get("squareMeter") is not None:
        updates["size_sqm"] = int(details["squareMeter"])
    if details.get("roomsCount") is not None:
        updates["rooms"] = float(details["roomsCount"])
    return listing.model_copy(update=updates) if updates else listing
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_yad2_detail.py -v` — all PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/sources/yad2_parse.py backend/tests/fixtures/yad2_item_detail.json backend/tests/test_yad2_detail.py
git commit -m "feat: add yad2 detail parsing and enrichment application"
```

---

### Task 5: Yad2Source HTTP client

**Files:**
- Create: `backend/apt/sources/yad2.py`
- Test: `backend/tests/test_yad2_source.py`

**Interfaces:**
- Consumes: Tasks 2–4; `SourceError` from Task 1; URL templates + `DEFAULT_HEADERS` + `USER_AGENT` **verbatim from the notes file §1–2**.
- Produces (`apt.sources.yad2.Yad2Source`) — satisfies the `Source` protocol:
  - `Yad2Source(min_delay: float = 2.0, max_delay: float = 8.0)`; attribute `name = "yad2"`.
  - `async fetch(locations) -> list[Listing]`: groups locations by `resolve()` (unknown cities logged + skipped); one build_id fetch per `fetch()` call (cached on the instance) via `__NEXT_DATA__` script → `json["buildId"]`; pages each query with params `{area, city, page}` up to `min(totalPages, MAX_PAGES_PER_QUERY)`; keeps only listings matching one of that query's locations (normalized city equality; when the location has a neighborhood, normalized neighborhood equality too); dedupes by token across queries; randomized `uniform(min_delay, max_delay)` sleep between successive page fetches; remembers each kept token's `route_slug` for `enrich`.
  - `async enrich(listing) -> Listing`: fetches the item-detail JSON and applies it; ANY failure logs a warning and returns the listing unchanged (enrichment is best-effort).
  - Retries in `_get_json`: statuses {500, 502, 503, 504}, 3 attempts, `await asyncio.sleep(2 ** attempt)` between; then `SourceError`. Non-retryable HTTP errors raise via `raise_for_status()`.
  - `aiohttp.ClientTimeout(total=30)` passed to every `ClientSession`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_yad2_source.py`:

```python
import json

import pytest
from aioresponses import aioresponses

from apt.domain.models import Location
from apt.sources.yad2 import RENT_DATA_URL, RENT_PAGE_URL, Yad2Source
from apt.sources.yad2_locations import KNOWN_CITIES

BIALIK = KNOWN_CITIES["קריית ביאליק"]
BUILD_ID = "build-xyz"

NEXT_DATA_HTML = (
    '<html><body><script id="__NEXT_DATA__" type="application/json">'
    + json.dumps({"buildId": BUILD_ID})
    + "</script></body></html>"
)


def feed_page(items, total_pages=1):
    return {
        "pageProps": {"dehydratedState": {"queries": [{
            "queryKey": ["realestate-rent-feed"],
            "state": {"data": {
                "pagination": {"totalPages": total_pages, "total": len(items)},
                "feed": items,
            }},
        }]}}
    }


def feed_item(token, city, price=5000, neighborhood=""):
    return {
        "token": token,
        "price": price,
        "address": {
            "city": {"text": city},
            "neighborhood": {"text": neighborhood},
            "street": {"text": ""},
            "house": {"floor": 1},
        },
        "additionalDetails": {"roomsCount": 3.0, "squareMeter": 70},
        "metaData": {"images": []},
        "tags": [],
    }


def rent_page_url():
    return RENT_PAGE_URL.format(route_slug=BIALIK.route_slug, area=BIALIK.area_id, city=BIALIK.city_id)


def data_url(page):
    base = RENT_DATA_URL.format(build_id=BUILD_ID, route_slug=BIALIK.route_slug)
    return f"{base}?area={BIALIK.area_id}&city={BIALIK.city_id}&page={page}"


def make_source():
    return Yad2Source(min_delay=0, max_delay=0)


async def test_fetch_returns_matching_listings():
    with aioresponses() as mocked:
        mocked.get(rent_page_url(), body=NEXT_DATA_HTML)
        mocked.get(
            data_url(1),
            payload=feed_page([
                feed_item("a1", "קריית ביאליק"),
                feed_item("elsewhere", "נהריה"),
            ]),
        )
        listings = await make_source().fetch([Location(city="קריית ביאליק")])
    assert [listing.source_id for listing in listings] == ["a1"]


async def test_fetch_paginates_and_dedupes():
    with aioresponses() as mocked:
        mocked.get(rent_page_url(), body=NEXT_DATA_HTML)
        mocked.get(data_url(1), payload=feed_page([feed_item("a1", "קריית ביאליק")], total_pages=2))
        mocked.get(data_url(2), payload=feed_page([feed_item("a1", "קריית ביאליק"), feed_item("a2", "קריית ביאליק")], total_pages=2))
        listings = await make_source().fetch([Location(city="קריית ביאליק")])
    assert sorted(listing.source_id for listing in listings) == ["a1", "a2"]


async def test_fetch_retries_server_errors():
    with aioresponses() as mocked:
        mocked.get(rent_page_url(), body=NEXT_DATA_HTML)
        mocked.get(data_url(1), status=503)
        mocked.get(data_url(1), payload=feed_page([feed_item("a1", "קריית ביאליק")]))
        listings = await make_source().fetch([Location(city="קריית ביאליק")])
    assert [listing.source_id for listing in listings] == ["a1"]


async def test_fetch_unknown_city_skipped_entirely():
    source = make_source()
    listings = await source.fetch([Location(city="עיר לא ממופה")])
    assert listings == []


async def test_fetch_neighborhood_location_requires_hood_match():
    haifa = KNOWN_CITIES["חיפה"]
    page_url = RENT_PAGE_URL.format(route_slug=haifa.route_slug, area=haifa.area_id, city=haifa.city_id)
    base = RENT_DATA_URL.format(build_id=BUILD_ID, route_slug=haifa.route_slug)
    with aioresponses() as mocked:
        mocked.get(page_url, body=NEXT_DATA_HTML)
        mocked.get(
            f"{base}?area={haifa.area_id}&city={haifa.city_id}&page=1",
            payload=feed_page([
                feed_item("in-hood", "חיפה", neighborhood="קריית חיים מערבית"),
                feed_item("other-hood", "חיפה", neighborhood="הדר"),
            ]),
        )
        listings = await make_source().fetch(
            [Location(city="חיפה", neighborhood="קריית חיים מערבית")]
        )
    assert [listing.source_id for listing in listings] == ["in-hood"]


async def test_enrich_failure_returns_listing_unchanged(caplog):
    source = make_source()
    with aioresponses() as mocked:
        mocked.get(rent_page_url(), body=NEXT_DATA_HTML)
        mocked.get(data_url(1), payload=feed_page([feed_item("a1", "קריית ביאליק")]))
        listings = await source.fetch([Location(city="קריית ביאליק")])
        enriched = await source.enrich(listings[0])
    assert enriched == listings[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_yad2_source.py -v` — FAIL with `ModuleNotFoundError: No module named 'apt.sources.yad2'`.

- [ ] **Step 3: Implement**

`backend/apt/sources/yad2.py` — copy `USER_AGENT` and `DEFAULT_HEADERS` **verbatim from the notes file §2**:

```python
import asyncio
import json
import logging
import random

import aiohttp
from bs4 import BeautifulSoup

from apt.domain.models import Listing, Location
from apt.sources import yad2_parse
from apt.sources.base import SourceError
from apt.sources.yad2_locations import Yad2Query, normalize_text, resolve

logger = logging.getLogger(__name__)

RENT_PAGE_URL = "https://www.yad2.co.il/realestate/rent/{route_slug}?area={area}&city={city}"
RENT_DATA_URL = "https://www.yad2.co.il/realestate/_next/data/{build_id}/rent/{route_slug}.json"
ITEM_DATA_URL = "https://www.yad2.co.il/realestate/_next/data/{build_id}/item/{route_slug}/{token}.json"

USER_AGENT = "<verbatim from notes §2>"
DEFAULT_HEADERS = {  # verbatim from notes §2
    ...
}

REQUEST_TIMEOUT_SECONDS = 30
MAX_PAGES_PER_QUERY = 10
RETRY_STATUSES = {500, 502, 503, 504}


def _matches_any(listing: Listing, locations: list[Location]) -> bool:
    for location in locations:
        if normalize_text(listing.city) != normalize_text(location.city):
            continue
        if location.neighborhood is None:
            return True
        if normalize_text(listing.neighborhood) == normalize_text(location.neighborhood):
            return True
    return False


class Yad2Source:
    name = "yad2"

    def __init__(self, min_delay: float = 2.0, max_delay: float = 8.0):
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._build_id: str | None = None
        self._route_slug_by_token: dict[str, str] = {}

    @staticmethod
    def _timeout() -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

    async def _sleep_politely(self) -> None:
        await asyncio.sleep(random.uniform(self._min_delay, self._max_delay))

    async def _fetch_build_id(self, session: aiohttp.ClientSession, query: Yad2Query) -> str:
        if self._build_id is not None:
            return self._build_id
        url = RENT_PAGE_URL.format(
            route_slug=query.route_slug, area=query.area_id, city=query.city_id
        )
        async with session.get(url) as response:
            response.raise_for_status()
            html = await response.text()
        script = BeautifulSoup(html, "html.parser").find("script", id="__NEXT_DATA__")
        if script is None or not script.string:
            raise SourceError("yad2: __NEXT_DATA__ script not found")
        self._build_id = json.loads(script.string)["buildId"]
        return self._build_id

    async def _get_json(self, session: aiohttp.ClientSession, url: str, params=None) -> dict:
        for attempt in range(3):
            async with session.get(url, params=params) as response:
                if response.status in RETRY_STATUSES:
                    await asyncio.sleep(2**attempt)
                    continue
                response.raise_for_status()
                return await response.json()
        raise SourceError(f"yad2: server errors persisted for {url}")

    async def fetch(self, locations: list[Location]) -> list[Listing]:
        grouped: dict[Yad2Query, list[Location]] = {}
        for location in locations:
            query = resolve(location)
            if query is None:
                logger.warning("yad2: no city mapping for %r - skipped", location.city)
                continue
            grouped.setdefault(query, []).append(location)

        results: list[Listing] = []
        seen: set[str] = set()
        async with aiohttp.ClientSession(headers=DEFAULT_HEADERS, timeout=self._timeout()) as session:
            first_request = True
            for query, query_locations in grouped.items():
                build_id = await self._fetch_build_id(session, query)
                url = RENT_DATA_URL.format(build_id=build_id, route_slug=query.route_slug)
                page, pages_total = 1, 1
                while page <= pages_total:
                    if not first_request:
                        await self._sleep_politely()
                    first_request = False
                    data = await self._get_json(
                        session, url,
                        params={"area": query.area_id, "city": query.city_id, "page": page},
                    )
                    feed = yad2_parse.extract_feed(data)
                    reported_pages = yad2_parse.total_pages(feed)
                    if reported_pages > MAX_PAGES_PER_QUERY:
                        logger.warning(
                            "yad2: %s reports %d pages, scraping first %d only",
                            query.route_slug, reported_pages, MAX_PAGES_PER_QUERY,
                        )
                    pages_total = min(reported_pages, MAX_PAGES_PER_QUERY)
                    for listing in yad2_parse.parse_feed_items(feed):
                        if listing.source_id in seen or not _matches_any(listing, query_locations):
                            continue
                        seen.add(listing.source_id)
                        self._route_slug_by_token[listing.source_id] = query.route_slug
                        results.append(listing)
                    page += 1
        return results

    async def enrich(self, listing: Listing) -> Listing:
        route_slug = self._route_slug_by_token.get(listing.source_id)
        if route_slug is None or self._build_id is None:
            return listing
        url = ITEM_DATA_URL.format(
            build_id=self._build_id, route_slug=route_slug, token=listing.source_id
        )
        try:
            async with aiohttp.ClientSession(headers=DEFAULT_HEADERS, timeout=self._timeout()) as session:
                data = await self._get_json(session, url)
        except Exception as exc:
            logger.warning("yad2: detail fetch failed for %s: %s", listing.source_id, exc)
            return listing
        return yad2_parse.apply_item_detail(listing, yad2_parse.extract_item_detail(data))
```

(The two `<verbatim>` markers mean: open the notes file and copy §2's `USER_AGENT` string and full `DEFAULT_HEADERS` dict exactly.)

- [ ] **Step 4: Run tests to verify they pass, then the whole suite**

Run: `pytest tests/test_yad2_source.py -v` — all PASS. Then `pytest` — everything green.

- [ ] **Step 5: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/sources/yad2.py backend/tests/test_yad2_source.py
git commit -m "feat: add yad2 source http client"
```

---

### Task 6: Scrape cycle orchestrator

**Files:**
- Create: `backend/apt/cycle.py`
- Test: `backend/tests/test_cycle.py`

**Interfaces:**
- Consumes: everything above + plan 1 repos (`ListingRepo`, `AlertRepo.list_active`, `ScrapeSetRepo.active_locations`, `SourceStateRepo`), `listing_matches`.
- Produces (`apt.cycle`):
  - `merge_preserving_enrichment(existing: Listing | None, incoming: Listing) -> Listing` — pure: incoming wins, EXCEPT description (keep existing non-empty when incoming empty), has_mamad/has_elevator (keep existing non-None when incoming None), entry_date (keep existing non-None when incoming None).
  - `async run_cycle(conn, sources: list[Source], notifier: Notifier, now: datetime) -> list[MatchEvent]` — the loop plan 3's bot and plan 6's deploy run every 15 minutes:
    1. `locations = ScrapeSetRepo(conn).active_locations(now)`; empty → return `[]` without touching sources.
    2. Per source: skip when `SourceStateRepo.get(name).enabled` is False; `fetch(locations)`; any exception → `record_run(name, now, error=str(exc))`, continue to next source.
    3. Per fetched listing: merge-preserve against existing, `upsert`; when new: `enrich` + re-upsert if changed.
    4. Events: `is_new` → kind "new"; else `price_changed and old_price is not None and new price < old_price` → kind "price_drop" with old_price. Match every event listing against all active alerts via `listing_matches`; one `MatchEvent` per (alert, listing).
    5. `record_run(name, now)` on source success; finally `await notifier.send(event)` for every event; return events.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_cycle.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from apt.cycle import merge_preserving_enrichment, run_cycle
from apt.domain.models import AlertFilters, Listing, Location
from apt.notify.base import LogNotifier
from apt.repo.alerts import AlertRepo
from apt.repo.listings import ListingRepo
from apt.repo.source_state import SourceStateRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(minutes=15)


class FakeSource:
    def __init__(self, name="yad2", listings=None, error=None, enrich_description=None):
        self.name = name
        self.listings = listings or []
        self.error = error
        self.enrich_description = enrich_description
        self.fetch_calls = 0
        self.enriched_tokens = []

    async def fetch(self, locations):
        self.fetch_calls += 1
        if self.error:
            raise self.error
        return list(self.listings)

    async def enrich(self, listing):
        self.enriched_tokens.append(listing.source_id)
        if self.enrich_description:
            return listing.model_copy(update={"description": self.enrich_description})
        return listing


def make_listing(token="a1", city="חיפה", price=5000, **overrides):
    base = dict(source="yad2", source_id=token, url=f"https://e.com/{token}", city=city, price=price)
    base.update(overrides)
    return Listing(**base)


def setup_alert(conn, filters=None):
    user = UserRepo(conn).upsert_google_user("g-1", "a@b.com", NOW)
    return AlertRepo(conn).create(user.id, "watch", filters or AlertFilters(locations=[Location(city="חיפה")]), ["telegram"], NOW)


def test_merge_preserving_enrichment():
    existing = make_listing(description="נוף לים", has_mamad=True, has_elevator=False)
    incoming = make_listing(price=4800)
    merged = merge_preserving_enrichment(existing, incoming)
    assert merged.price == 4800
    assert merged.description == "נוף לים"
    assert merged.has_mamad is True
    assert merged.has_elevator is False
    assert merge_preserving_enrichment(None, incoming) == incoming


async def test_new_listing_produces_event_and_notification(conn):
    alert = setup_alert(conn)
    source = FakeSource(listings=[make_listing()])
    notifier = LogNotifier()
    events = await run_cycle(conn, [source], notifier, NOW)
    assert len(events) == 1
    assert events[0].kind == "new"
    assert events[0].alert.id == alert.id
    assert notifier.sent == events
    assert SourceStateRepo(conn).get("yad2").last_success == NOW.isoformat()


async def test_second_cycle_same_data_no_events(conn):
    setup_alert(conn)
    source = FakeSource(listings=[make_listing()])
    await run_cycle(conn, [source], LogNotifier(), NOW)
    events = await run_cycle(conn, [source], LogNotifier(), LATER)
    assert events == []


async def test_price_drop_produces_event_price_rise_does_not(conn):
    setup_alert(conn)
    await run_cycle(conn, [FakeSource(listings=[make_listing(price=5000)])], LogNotifier(), NOW)
    drop_events = await run_cycle(conn, [FakeSource(listings=[make_listing(price=4500)])], LogNotifier(), LATER)
    assert [event.kind for event in drop_events] == ["price_drop"]
    assert drop_events[0].old_price == 5000
    rise_events = await run_cycle(
        conn, [FakeSource(listings=[make_listing(price=9000)])], LogNotifier(), LATER + timedelta(minutes=15)
    )
    assert rise_events == []


async def test_non_matching_listing_no_event(conn):
    setup_alert(conn, AlertFilters(locations=[Location(city="תל אביב")]))
    events = await run_cycle(conn, [FakeSource(listings=[make_listing(city="חיפה")])], LogNotifier(), NOW)
    assert events == []


async def test_no_active_locations_skips_sources(conn):
    source = FakeSource(listings=[make_listing()])
    events = await run_cycle(conn, [source], LogNotifier(), NOW)
    assert events == []
    assert source.fetch_calls == 0


async def test_disabled_source_skipped(conn):
    setup_alert(conn)
    SourceStateRepo(conn).set_enabled("yad2", False)
    source = FakeSource(listings=[make_listing()])
    events = await run_cycle(conn, [source], LogNotifier(), NOW)
    assert events == []
    assert source.fetch_calls == 0


async def test_failing_source_recorded_others_continue(conn):
    setup_alert(conn)
    bad = FakeSource(name="facebook", error=RuntimeError("session expired"))
    good = FakeSource(name="yad2", listings=[make_listing()])
    events = await run_cycle(conn, [bad, good], LogNotifier(), NOW)
    assert len(events) == 1
    state = SourceStateRepo(conn).get("facebook")
    assert state.last_error == "session expired"
    assert SourceStateRepo(conn).get("yad2").last_error is None


async def test_enrichment_only_for_new_and_persisted(conn):
    setup_alert(conn)
    source = FakeSource(listings=[make_listing()], enrich_description="חדש ומרוהט")
    await run_cycle(conn, [source], LogNotifier(), NOW)
    assert source.enriched_tokens == ["a1"]
    assert ListingRepo(conn).get("yad2:a1").description == "חדש ומרוהט"
    again = FakeSource(listings=[make_listing()])
    await run_cycle(conn, [again], LogNotifier(), LATER)
    assert again.enriched_tokens == []
    assert ListingRepo(conn).get("yad2:a1").description == "חדש ומרוהט"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cycle.py -v` — FAIL with `ModuleNotFoundError: No module named 'apt.cycle'`.

- [ ] **Step 3: Implement**

`backend/apt/cycle.py`:

```python
import logging
import sqlite3
from datetime import datetime

from apt.domain.events import MatchEvent
from apt.domain.matching import listing_matches
from apt.domain.models import Listing
from apt.notify.base import Notifier
from apt.repo.alerts import AlertRepo
from apt.repo.listings import ListingRepo
from apt.repo.scrape_set import ScrapeSetRepo
from apt.repo.source_state import SourceStateRepo
from apt.sources.base import Source

logger = logging.getLogger(__name__)


def merge_preserving_enrichment(existing: Listing | None, incoming: Listing) -> Listing:
    """Feed items lack detail-only fields; keep known values instead of erasing them."""
    if existing is None:
        return incoming
    updates: dict = {}
    if not incoming.description and existing.description:
        updates["description"] = existing.description
    if incoming.has_mamad is None and existing.has_mamad is not None:
        updates["has_mamad"] = existing.has_mamad
    if incoming.has_elevator is None and existing.has_elevator is not None:
        updates["has_elevator"] = existing.has_elevator
    if incoming.entry_date is None and existing.entry_date is not None:
        updates["entry_date"] = existing.entry_date
    return incoming.model_copy(update=updates) if updates else incoming


async def run_cycle(
    conn: sqlite3.Connection,
    sources: list[Source],
    notifier: Notifier,
    now: datetime,
) -> list[MatchEvent]:
    locations = ScrapeSetRepo(conn).active_locations(now)
    if not locations:
        logger.info("cycle: no active locations - nothing to scrape")
        return []

    listings_repo = ListingRepo(conn)
    state_repo = SourceStateRepo(conn)
    alerts = AlertRepo(conn).list_active()
    events: list[MatchEvent] = []

    for source in sources:
        if not state_repo.get(source.name).enabled:
            logger.info("cycle: source %s disabled - skipped", source.name)
            continue
        try:
            fetched = await source.fetch(locations)
        except Exception as exc:
            logger.error("cycle: source %s failed: %s", source.name, exc)
            state_repo.record_run(source.name, now, error=str(exc))
            continue

        for listing in fetched:
            merged = merge_preserving_enrichment(listings_repo.get(listing.id), listing)
            result = listings_repo.upsert(merged, now)
            final = merged
            if result.is_new:
                final = await source.enrich(merged)
                if final != merged:
                    listings_repo.upsert(final, now)

            if result.is_new:
                kind, old_price = "new", None
            elif (
                result.price_changed
                and result.old_price is not None
                and final.price is not None
                and final.price < result.old_price
            ):
                kind, old_price = "price_drop", result.old_price
            else:
                continue

            for alert in alerts:
                if listing_matches(final, alert.filters):
                    events.append(
                        MatchEvent(kind=kind, listing=final, alert=alert, old_price=old_price)
                    )

        state_repo.record_run(source.name, now)
        logger.info("cycle: source %s returned %d listings", source.name, len(fetched))

    for event in events:
        await notifier.send(event)
    return events
```

- [ ] **Step 4: Run tests to verify they pass, then the whole suite**

Run: `pytest tests/test_cycle.py -v` — all PASS. Then `pytest` — everything green.

- [ ] **Step 5: Commit**

```bash
cd /Users/alon.i/APT
git add backend/apt/cycle.py backend/tests/test_cycle.py
git commit -m "feat: add scrape cycle orchestrator"
```

---

### Task 7: Scraper service entrypoint + docs

**Files:**
- Create: `backend/apt/scraper_main.py`
- Modify: `backend/README.md`
- Test: `backend/tests/test_scraper_main.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `python -m apt.scraper_main` — the long-running scraper service (plan 6 wraps it in a container). Env config: `APT_DB_PATH` (default `data/apt.db`), `APT_SCRAPE_INTERVAL_SECONDS` (default `900`).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_scraper_main.py`:

```python
from apt import scraper_main


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("APT_DB_PATH", raising=False)
    monkeypatch.delenv("APT_SCRAPE_INTERVAL_SECONDS", raising=False)
    config = scraper_main.load_config()
    assert str(config.db_path) == "data/apt.db"
    assert config.interval_seconds == 900


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("APT_DB_PATH", "/tmp/x.db")
    monkeypatch.setenv("APT_SCRAPE_INTERVAL_SECONDS", "60")
    config = scraper_main.load_config()
    assert str(config.db_path) == "/tmp/x.db"
    assert config.interval_seconds == 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scraper_main.py -v` — FAIL with `ImportError`.

- [ ] **Step 3: Implement**

`backend/apt/scraper_main.py`:

```python
import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from apt.cycle import run_cycle
from apt.notify.base import LogNotifier
from apt.repo.db import connect, migrate
from apt.sources.yad2 import Yad2Source

logger = logging.getLogger(__name__)


class ScraperConfig(BaseModel):
    db_path: Path
    interval_seconds: int


def load_config() -> ScraperConfig:
    return ScraperConfig(
        db_path=Path(os.getenv("APT_DB_PATH", "data/apt.db")),
        interval_seconds=int(os.getenv("APT_SCRAPE_INTERVAL_SECONDS", "900")),
    )


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    config = load_config()
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(config.db_path)
    migrate(conn)
    notifier = LogNotifier()
    logger.info("scraper started (db=%s, interval=%ss)", config.db_path, config.interval_seconds)
    while True:
        # A fresh source per cycle re-discovers the build_id, surviving Yad2 redeploys.
        source = Yad2Source()
        try:
            events = await run_cycle(conn, [source], notifier, datetime.now(timezone.utc))
            logger.info("cycle finished: %d match events", len(events))
        except Exception:
            logger.exception("cycle crashed; retrying next interval")
        await asyncio.sleep(config.interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Update backend/README.md**

Replace the `## Layout` section content with:

```markdown
## Layout

- `apt/domain/` — Pydantic models, match events, and the pure `listing_matches` function
- `apt/repo/` — SQLite (WAL) repositories; all persistence goes through here
- `apt/sources/` — listing sources; `yad2_parse` (pure parsing) + `yad2` (HTTP client) + city registry
- `apt/notify/` — notifier protocol; `LogNotifier` placeholder until plan 3's channels
- `apt/cycle.py` — the scrape-and-match cycle
- `apt/scraper_main.py` — scraper service entrypoint
```

and append after the Conventions section:

```markdown
## Running the scraper

```bash
APT_DB_PATH=data/apt.db APT_SCRAPE_INTERVAL_SECONDS=900 python -m apt.scraper_main
```

New Yad2 cities are added in `apt/sources/yad2_locations.py` (`KNOWN_CITIES`).
Yad2 endpoint/JSON contract: `docs/superpowers/specs/2026-07-07-yad2-reference-notes.md`.
```

- [ ] **Step 5: Run the full suite and commit**

Run: `pytest` — everything green.

```bash
cd /Users/alon.i/APT
git add backend/apt/scraper_main.py backend/tests/test_scraper_main.py backend/README.md
git commit -m "feat: add scraper service entrypoint"
```

---

## Plan 2 Exit Criteria

- Full suite green (plan 1's 60 tests + ~30 new).
- `run_cycle` produces `MatchEvent`s consumed by plan 3's real notifier; `Yad2Source` satisfies `Source`; `LogNotifier` satisfies `Notifier`.
- Live Yad2 behavior (real bucket names, build_id rotation) remains unverified by design — the notes file's "Live-Verification TODOs" carry into plan 6's canary task.
