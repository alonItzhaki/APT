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


def _to_number(value: Any, cast) -> int | float | None:
    if value is None:
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def parse_item(item: dict[str, Any]) -> Listing | None:
    token = item.get("token")
    if token is None or token == "":
        return None
    address = item.get("address") or {}
    city = _text(address.get("city"))
    if city is None:
        return None
    details = item.get("additionalDetails") or {}
    tags = [tag.get("name") for tag in item.get("tags") or [] if tag.get("name")]
    tag_text = " ".join(tags)
    token = str(token)
    return Listing(
        source="yad2",
        source_id=token,
        url=APARTMENT_PAGE_URL.format(token=token),
        city=city,
        neighborhood=_text(address.get("neighborhood")),
        street=_text(address.get("street")),
        price=_to_number(item.get("price"), int),
        rooms=_to_number(details.get("roomsCount"), float),
        size_sqm=_to_number(details.get("squareMeter"), int),
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
