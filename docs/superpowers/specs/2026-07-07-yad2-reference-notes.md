# Yad2 Scraper — Technical Reference Notes

**Date distilled:** 2026-07-07  
**Source files:** `yad2.py`, `shared_scrapers_config.py`  
**Purpose:** Ground-truth contract for a clean reimplementation; do not deviate from names/paths shown here.

---

## 1. Endpoints

### Rent page URL (build_id discovery)

```
RENT_PAGE_URL = "https://www.yad2.co.il/realestate/rent/{route_slug}?area={area}&city={city}"
```

Concretely, with the first entry of `DEFAULT_YAD2_LOCATION_FILTERS` (קריית ביאליק):

```
https://www.yad2.co.il/realestate/rent/coastal-north?area=6&city=9500
```

### build_id discovery mechanism

1. GET `RENT_PAGE_URL` with `DEFAULT_HEADERS`.
2. Parse response HTML with BeautifulSoup.
3. Find `<script id="__NEXT_DATA__">` — read its `.string`, parse as JSON.
4. Extract `data["buildId"]` — this is the build_id string.
5. No regex is used; it is pure JSON key access on the `__NEXT_DATA__` script block.
6. The build_id is cached on the `ApartmentScraper` instance (`self.build_id`). It is fetched at most once per scraper instance lifetime (lazy, via `_ensure_build_id`). There is **no TTL or expiry check** beyond the instance scope — if the server rotates it mid-run the scraper will start receiving errors.

### Feed data URL template (`RENT_DATA_URL`)

```
https://www.yad2.co.il/realestate/_next/data/{build_id}/rent/{route_slug}.json
```

**Always-present query parameters:**

| Param | Source | Example |
|-------|--------|---------|
| `area` | `location['area']` (int) | `6` |
| `city` | `location['city']` (int) | `9500` |
| `page` | page number (int, 1-based) | `1` |

**Conditionally-added query parameters:**

| Param | Condition | Source |
|-------|-----------|--------|
| `neighborhood` | `location.get('neighborhood') is not None` | `location['neighborhood']` (int) |
| `bBox` | `location.get('bBox') is not None` | `location['bBox']` (string, `"lat1,lon1,lat2,lon2"`) |
| `zoom` | `location.get('zoom') is not None` | `location['zoom']` (int) |
| `multiNeighborhood` | `self.multi_neighborhoods_str` is non-empty | comma-separated int string |

**Note:** There are **no price/rooms/squareMeter filter params** in the URL. All numeric filtering is done client-side after fetching.

**Default bBox and zoom from config:**
```python
DEFAULT_YAD2_BBOX = "32.728229,34.863183,32.970433,35.320162"
DEFAULT_YAD2_ZOOM = 10
```

### Item detail URL template (`ITEM_DATA_URL`)

```
https://www.yad2.co.il/realestate/_next/data/{build_id}/item/{route_slug}/{token}.json
```

### Apartment page URL template (for display only)

```
https://www.yad2.co.il/realestate/item/{token}
```

---

## 2. Headers

Exact `DEFAULT_HEADERS` dict (also used for both feed and detail requests):

```python
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'

DEFAULT_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Priority': 'u=0, i',
    'Sec-Ch-Ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': USER_AGENT,
}
```

These same headers are used for **all three** request types: build_id page, feed data, item detail.

---

## 3. Feed JSON Structure

### Path to listing items

The raw JSON response from the feed URL is a Next.js `_next/data` payload. Navigation:

```
response_json
  └── pageProps                          # dict
        └── dehydratedState              # dict
              └── queries                # list of query dicts
                    └── [n]              # iterate until match
                          queryKey[0] == "realestate-rent-feed"
                          └── state
                                └── data # dict — this is feed_data
```

`feed_data` is the dict returned by `_extract_feed`. It contains **named bucket keys** (e.g. `"feed"`, `"promoted"`, etc. — exact bucket names are **not hardcoded** in the scraper; it iterates all keys) plus the reserved keys `"pagination"` and `"lookalike"`.

### Iterating listing items (`_process_page`)

```python
for bucket_name, bucket_items in feed_data.items():
    if bucket_name in {'pagination', 'lookalike'}:
        continue
    if isinstance(bucket_items, list):
        for item in bucket_items:
            ...
```

All list-valued buckets that are not `pagination` or `lookalike` are treated as listing item arrays.

### Pagination info

```
feed_data["pagination"]["totalPages"]  # int — total number of pages
feed_data["pagination"]["total"]       # int — total item count
```

---

## 4. Item Fields

All paths are relative to a single item dict (one element from a bucket list inside `feed_data`).

| Output field | JSON key path in item | Transformation |
|---|---|---|
| `id` | `item["token"]` | Used as-is (string) |
| `price` | `item["price"]` | Raw value (int/None) |
| `city` | `item["address"]["city"]["text"]` | String |
| `area` | `item["address"]["region"]["text"]` | String |
| `hood` | `item["address"]["neighborhood"]["text"]` | String |
| `street` | `item["address"]["street"]["text"]` | String |
| `location` | Composed from `street`, `hood`, `city` | `", ".join(deduped_non_empty_parts)` |
| `latitude` | `item["address"]["coords"]["lat"]` | Raw |
| `longitude` | `item["address"]["coords"]["lon"]` | Raw |
| `rooms` | `item["additionalDetails"]["roomsCount"]` | `str(value)` |
| `size` | `item["additionalDetails"]["squareMeter"]` | `str(value)` |
| `floor` | `item["address"]["house"]["floor"]` | `str(floor) if floor is not None else ''` |
| `images` | `item["metaData"]["images"]` | List (raw) |
| `tags` | `item["tags"]` | `[tag["name"] for tag in tags]` — list of strings |
| `is_mamad` | derived from `tags` | `'ממ"ד' in tag_text or 'ממד' in tag_text` where `tag_text = " ".join(tags)` |
| `is_elevator` | derived from `tags` | `'מעלית' in tag_text` |
| `apartment_page_url` | constructed | `f"https://www.yad2.co.il/realestate/item/{item['token']}"` |
| `md5` | computed | `hashlib.md5(str({'location': ..., 'price': ...}).encode()).hexdigest()` |
| `type` | hardcoded | `"yad2"` |

**Floor extraction detail (`_extract_floor`):**
```python
address = item.get('address', {})
house_details = address.get('house', {})
floor = house_details.get('floor', '')
return str(floor) if floor is not None else ''
```
Note: `get('floor', '')` returns `''` if key absent, but the explicit `if floor is not None` means that `''` would be returned as `''` (not None) — only actual `None` values produce `''`. Integers including `0` are stringified.

**Note:** `description` is **not extracted** from the feed item. It is only added during detail enrichment (see Section 5).

---

## 5. Detail Enrichment

### When it runs

Only when `self.require_mamad is not None` OR `self.require_elevator is not None`. Otherwise `_enrich_and_filter_amenities` is a no-op pass-through.

### Detail response navigation (`_extract_item_detail`)

Same structure as the feed response:

```
detail_response_json
  └── pageProps
        └── dehydratedState
              └── queries
                    └── [n]
                          queryKey[0] == "item"   # <-- different sentinel from feed
                          └── state
                                └── data          # dict — this is detail_item
```

### Fields added/overwritten by `_apply_item_detail`

All paths relative to `detail_item`:

| Output field | JSON key path | Condition |
|---|---|---|
| `is_mamad` | `detail_item["inProperty"]["includeSecurityRoom"]` | Only written if key `"includeSecurityRoom"` exists in `inProperty` |
| `is_elevator` | `detail_item["inProperty"]["includeElevator"]` | Only written if key `"includeElevator"` exists in `inProperty` |
| `description` | `detail_item["metaData"]["description"]` | Only written if truthy |
| `size` | `detail_item["additionalDetails"]["squareMeter"]` | Only written if not None; overrides feed value |
| `rooms` | `detail_item["additionalDetails"]["roomsCount"]` | Only written if not None; overrides feed value |

**Key semantics:** Detail enrichment uses `in` membership check (`'includeSecurityRoom' in in_property`) so that a key explicitly set to `False` is still applied, while a missing key leaves the tag-derived value from the feed intact.

---

## 6. Filtering

### `_matches_filters` — numeric filters (applied to processed item)

All fields already on the processed item (post `_process_item`):

| Filter | Field | Type coercion | Semantics |
|---|---|---|---|
| `min_price` / `max_price` | `item["price"]` | raw int | `None` price fails both min and max checks |
| `min_rooms` / `max_rooms` | `item["rooms"]` | `float(rooms_value)` — `''` or `None` → `None` | `None` rooms fails both min and max checks |
| `min_squaremeter` | `item["size"]` | `float(size_value)` — `''` or `None` → `None` | `None` size fails the min check |
| `min_floor` / `max_floor` | `item["floor"]` | `int(floor_value) if str(floor_value).isdigit() else None` | `None` floor fails both min and max checks |

If a filter threshold is `None` (not set), that constraint is skipped entirely.

### `_matches_amenity_filters`

```python
if self.require_mamad is not None and bool(item.get('is_mamad')) != self.require_mamad:
    return False
if self.require_elevator is not None and bool(item.get('is_elevator')) != self.require_elevator:
    return False
```

Amenity filters are only evaluated **after** detail enrichment (which may overwrite `is_mamad`/`is_elevator`).

### `_matches_location`

Normalization applied to both sides before comparison:

```python
def _normalize_text(value: str) -> str:
    value = (value or '').replace('קריית', 'קרית')
    return ''.join(value.split()).casefold()
```

- Collapses all whitespace, lowercases (Unicode casefold).
- Replaces `קריית` with `קרית` to normalize Hebrew spelling variants.

Match logic:

```python
if location.get('match_field') == 'hood':
    return _normalize_text(item['hood']) == _normalize_text(location['name'])
else:
    return _normalize_text(item['city']) == _normalize_text(location['name'])
```

---

## 7. Location Model

### Location dict schema

```python
{
    "name":        str,         # display name / match target
    "city":        int,         # city_id
    "area":        int,         # area_id
    "route_slug":  str,         # URL path segment
    "bBox":        str | None,  # "lat_sw,lon_sw,lat_ne,lon_ne"
    "zoom":        int | None,
    "neighborhood": int | None, # neighborhood_id (optional)
    "match_field": "hood" | "city",
}
```

### `KNOWN_CITIES` (verbatim from config)

```python
KNOWN_CITIES = {
    "תל אביב":        {"city_id": 5000, "area_id": 1, "route_slug": "tel-aviv-area"},
    "חיפה":           {"city_id": 4000, "area_id": 5, "route_slug": "coastal-north"},
    "קריית ים":       {"city_id": 9600, "area_id": 6, "route_slug": "coastal-north"},
    "קריית מוצקין":   {"city_id": 8200, "area_id": 6, "route_slug": "coastal-north"},
    "קריית ביאליק":   {"city_id": 9500, "area_id": 6, "route_slug": "coastal-north"},
}
```

### `KNOWN_HOODS` (verbatim from config)

```python
KNOWN_HOODS = {
    "קריית חיים מערבית": {"city_id": 4000, "area_id": 5, "neighborhood_id": 648, "route_slug": "coastal-north"},
    "קריית חיים מזרחית": {"city_id": 4000, "area_id": 5, "neighborhood_id": 650, "route_slug": "coastal-north"},
}
```

### `DEFAULT_YAD2_LOCATION_FILTERS` (how it is built)

```python
DEFAULT_SEARCH_LOCATIONS = [
    "קריית ים",
    "קריית חיים מערבית",
    "קריית חיים מזרחית",
    "קריית מוצקין",
    "קריית ביאליק",
]

DEFAULT_YAD2_LOCATION_FILTERS = [
    {
        "name": location_name,
        "city": KNOWN_CITIES["קריית ביאליק"]["city_id"],   # 9500 — SAME for all entries (intentional!)
        "area": KNOWN_CITIES["קריית ביאליק"]["area_id"],   # 6 — SAME for all entries
        "route_slug": KNOWN_CITIES["קריית ביאליק"]["route_slug"],  # "coastal-north"
        "bBox": "32.728229,34.863183,32.970433,35.320162",
        "zoom": 10,
        "match_field": "hood" if location_name in KNOWN_HOODS else "city",
    }
    for location_name in DEFAULT_SEARCH_LOCATIONS
]
```

**Critical observation:** All 5 location entries use the same `city=9500`, `area=6`, `route_slug="coastal-north"` — the `bBox` is doing the geographic scoping. The `name` + `match_field` control client-side filtering of the results.

The resulting 5 entries, expanded:

| name | city | area | route_slug | bBox | zoom | match_field |
|---|---|---|---|---|---|---|
| קריית ים | 9500 | 6 | coastal-north | 32.728229,34.863183,32.970433,35.320162 | 10 | city |
| קריית חיים מערבית | 9500 | 6 | coastal-north | (same) | 10 | hood |
| קריית חיים מזרחית | 9500 | 6 | coastal-north | (same) | 10 | hood |
| קריית מוצקין | 9500 | 6 | coastal-north | (same) | 10 | city |
| קריית ביאליק | 9500 | 6 | coastal-north | (same) | 10 | city |

Note: neighborhood_id is NOT included in any of the default location entries (they rely on bBox instead).

---

## 8. Politeness / Pacing

### Timeouts

```python
REQUEST_TIMEOUT = 30          # seconds; passed as aiohttp.ClientTimeout(total=30)
CONNECT_TIMEOUT = 20          # defined in config but NOT used in yad2.py directly
SOCK_READ_TIMEOUT = 120       # defined in config but NOT used in yad2.py directly
```

**Note:** The `timeout` variable is constructed in `_get_page_data` (`aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)`) but is **not passed** to the `aiohttp.ClientSession()` constructor — it is a bug/dead code. The session for `_get_item_detail_data` also constructs no timeout. Effective timeout is therefore aiohttp's default.

### Delays

`MIN_DELAY_BETWEEN_REQUESTS = 2.0` and `MAX_DELAY_BETWEEN_REQUESTS = 8.0` are imported but **never used** in `yad2.py`. There is no `asyncio.sleep` between page requests.

### Retry behavior (`_get_page_data`)

- 3 attempts (`for attempt in range(3)`)
- Retries on HTTP status: `{500, 502, 503, 504}`
- Backoff: `2 ** attempt` seconds (0s, 2s, 4s for attempts 0, 1, 2)
- Raises `RuntimeError` after 3 failures
- `_get_item_detail_data` has **no retry logic** — errors are caught in the caller and logged as warnings, item is still included (with tag-derived amenity flags)

### Page caching

`get_current` maintains a `page_cache: Dict[tuple, Dict[str, Any]]` keyed by:

```python
cache_key = (
    location.get('route_slug'),
    location.get('area'),
    location.get('city'),
    location.get('bBox'),
    location.get('zoom'),
    location.get('neighborhood'),
    page_number,
)
```

Since all 5 default locations share identical `route_slug/area/city/bBox/zoom/neighborhood` values, **page 1 is fetched exactly once** and its response is reused for all 5 location entries. This is intentional — the bBox covers the entire region, and per-location filtering happens client-side.

### build_id caching

Cached on the instance: `self.build_id`. Fetched once on first call to `_ensure_build_id`. No refresh mechanism within a run.

---

## 9. Gotchas

1. **build_id expiry:** The build_id is a Next.js deployment identifier. If Yad2 deploys a new version mid-run, subsequent `_next/data` requests will return 404 or malformed data. The scraper has no recovery path for this — it will raise or return empty results silently.

2. **`timeout` is dead code in `_get_page_data`:** The `aiohttp.ClientTimeout` object is constructed but not passed to the session. Requests effectively use aiohttp's default timeout (5 minutes total).

3. **All default locations share the same API params:** Because `city=9500`, `area=6`, and `bBox` are identical for all 5 entries, the page cache will hit 100% after page 1 is fetched. All differentiation is client-side via `_matches_location`.

4. **`neighborhood` param is absent from defaults:** None of the 5 default location entries have a `neighborhood` key, so that param is never added to the URL. The `multiNeighborhood` param is only added if `ApartmentScraper` is initialized with `multi_neighborhoods`.

5. **Ad/promoted items are NOT explicitly filtered:** `_process_page` skips `pagination` and `lookalike` buckets but processes ALL other buckets indiscriminately. If Yad2 returns promoted/sponsored items in a bucket named something other than `lookalike`, they will be included.

6. **`is_mamad` tag detection uses two variants:** Both `'ממ"ד'` (with typographic quote) and `'ממד'` (without) are checked in the tag text. The detail endpoint's `includeSecurityRoom` is more reliable and will override the tag-based value if the detail fetch succeeds.

7. **Floor filtering uses `str(floor_value).isdigit()`:** This means floor `0` (ground floor, valid integer) will pass `isdigit()` and be filtered correctly. Negative floors (basements) will fail `isdigit()` and be treated as `None` — they will fail any `min_floor`/`max_floor` constraint.

8. **`_normalize_text` replaces `קריית` with `קרית`** before all location comparisons, so the scraper is tolerant of that common Hebrew spelling variant.

9. **Response shape variation:** `_extract_feed` and `_extract_item_detail` both return `{}` on any structural mismatch rather than raising. A missing `realestate-rent-feed` query key in the response will silently produce an empty page with no error.

10. **`description` only available after detail fetch:** The feed item has no `description` field. It is only populated if `_apply_item_detail` runs (i.e., when amenity filters are active). Items returned without amenity filter requirements will have no `description`.

---

## Minimal Synthetic Fixture

A compact JSON mimicking the feed response shape, suitable as a pytest fixture. Exercises all documented key paths.

```json
{
  "pageProps": {
    "dehydratedState": {
      "queries": [
        {
          "queryKey": ["realestate-rent-feed"],
          "state": {
            "data": {
              "pagination": {
                "totalPages": 2,
                "total": 3
              },
              "lookalike": [
                {
                  "token": "lookalike-token-skip",
                  "price": 1000
                }
              ],
              "feed": [
                {
                  "token": "abc123",
                  "price": 4500,
                  "address": {
                    "city":         {"text": "קריית ים"},
                    "region":       {"text": "חוף הכרמל"},
                    "neighborhood": {"text": ""},
                    "street":       {"text": "הרצל"},
                    "house":        {"floor": 3},
                    "coords":       {"lat": 32.85, "lon": 35.07}
                  },
                  "additionalDetails": {
                    "roomsCount": 3.5,
                    "squareMeter": 80
                  },
                  "metaData": {
                    "images": [
                      "https://img.yad2.co.il/Pics/abc123/1.jpg"
                    ]
                  },
                  "tags": [
                    {"name": "מעלית"},
                    {"name": "חניה"}
                  ]
                },
                {
                  "token": "def456",
                  "price": 5200,
                  "address": {
                    "city":         {"text": "חיפה"},
                    "region":       {"text": "חוף הכרמל"},
                    "neighborhood": {"text": "קריית חיים מערבית"},
                    "street":       {"text": "ביאליק"},
                    "house":        {"floor": 0},
                    "coords":       {"lat": 32.82, "lon": 35.01}
                  },
                  "additionalDetails": {
                    "roomsCount": 4.0,
                    "squareMeter": 95
                  },
                  "metaData": {
                    "images": []
                  },
                  "tags": [
                    {"name": "ממ\"ד"},
                    {"name": "מעלית"}
                  ]
                }
              ],
              "promoted": [
                {
                  "token": "promo999",
                  "price": 3800,
                  "address": {
                    "city":         {"text": "קריית מוצקין"},
                    "region":       {"text": "חוף הכרמל"},
                    "neighborhood": {"text": ""},
                    "street":       {"text": ""},
                    "house":        {"floor": null},
                    "coords":       {"lat": 32.83, "lon": 35.05}
                  },
                  "additionalDetails": {
                    "roomsCount": null,
                    "squareMeter": null
                  },
                  "metaData": {
                    "images": []
                  },
                  "tags": []
                }
              ]
            }
          }
        }
      ]
    }
  }
}
```

**What this fixture exercises:**

- `lookalike` bucket skipped by `_process_page`
- `feed` and `promoted` buckets both processed
- `abc123`: city match, floor=3 (integer floor), elevator tag, no mamad
- `def456`: hood match (`קריית חיים מערבית`), floor=0 (ground, `isdigit()` returns True), both mamad (with typographic quote) and elevator
- `promo999`: floor=null → empty string → `isdigit()` False → floor_number=None; rooms=null and size=null → both coerced to None in filter checks
- `pagination.totalPages=2` and `pagination.total=3`

**Corresponding detail response fixture** (for `_extract_item_detail` / `_apply_item_detail`):

```json
{
  "pageProps": {
    "dehydratedState": {
      "queries": [
        {
          "queryKey": ["item"],
          "state": {
            "data": {
              "inProperty": {
                "includeSecurityRoom": true,
                "includeElevator": false
              },
              "metaData": {
                "description": "דירה מרווחת עם נוף לים"
              },
              "additionalDetails": {
                "squareMeter": 85,
                "roomsCount": 3.5
              }
            }
          }
        }
      ]
    }
  }
}
```

---

## Live-Verification TODOs

These aspects could NOT be determined from the source alone and require a live run or Yad2 documentation:

1. **Exact bucket names** in `feed_data` beyond `feed`, `promoted`, `lookalike`. The scraper iterates all list-valued keys, so the real bucket names are unknown without a live API response.
2. **`token` field type:** Assumed string (used in URL construction), but could be int in the raw JSON — verify.
3. **Whether `address.house` always exists** or can be absent entirely (the scraper uses `.get('house', {})` which is safe, but the fixture should cover the missing-key case).
4. **Whether `multiNeighborhood` param is accepted by the API** or silently ignored — not verifiable from client code alone.
5. **build_id format** — not validated anywhere; assumed opaque string. Unclear if it has a TTL shorter than a typical scraper run.
6. **`image_only` and `price_only` constructor params** are stored but never used in any filter method visible in the code. Their intended semantics are unknown.
