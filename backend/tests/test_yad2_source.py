import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


def make_mock_response(body=None, json_data=None, status=200):
    """Create a mock response that works as a context manager."""
    response = AsyncMock()
    response.status = status
    response.raise_for_status = MagicMock()
    if body is not None:
        response.text = AsyncMock(return_value=body)
    if json_data is not None:
        response.json = AsyncMock(return_value=json_data)

    # Make it work as an async context manager
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    return response


def make_mock_session_with_responses(responses_map):
    """Create a mock session that returns appropriate responses for URLs."""
    session = AsyncMock()

    def mock_get(url, **kwargs):
        for pattern, response in responses_map.items():
            if callable(pattern) and pattern(url, kwargs):
                return response
        raise Exception(f"Unexpected URL: {url}")

    session.get = mock_get
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


async def test_fetch_returns_matching_listings():
    source = make_source()

    responses_map = {
        lambda url, kw: "/rent/" in url and ".json" not in url:
            make_mock_response(body=NEXT_DATA_HTML),
        lambda url, kw: "/_next/data/" in url and ".json" in url:
            make_mock_response(json_data=feed_page([
                feed_item("a1", "קריית ביאליק"),
                feed_item("elsewhere", "נהריה"),
            ])),
    }

    session = make_mock_session_with_responses(responses_map)

    with patch("apt.sources.yad2.aiohttp.ClientSession", return_value=session):
        listings = await source.fetch([Location(city="קריית ביאליק")])

    assert [listing.source_id for listing in listings] == ["a1"]


async def test_fetch_paginates_and_dedupes():
    source = make_source()

    responses_list = [
        feed_page([feed_item("a1", "קריית ביאליק")], total_pages=2),
        feed_page([feed_item("a1", "קריית ביאליק"), feed_item("a2", "קריית ביאליק")], total_pages=2),
    ]
    call_count = [0]

    def mock_get(url, **kwargs):
        if "/rent/" in url and ".json" not in url:
            return make_mock_response(body=NEXT_DATA_HTML)
        elif "/_next/data/" in url and ".json" in url:
            resp = make_mock_response(json_data=responses_list[call_count[0]])
            call_count[0] += 1
            return resp
        raise Exception(f"Unexpected URL: {url}")

    session = AsyncMock()
    session.get = mock_get
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    with patch("apt.sources.yad2.aiohttp.ClientSession", return_value=session):
        listings = await source.fetch([Location(city="קריית ביאליק")])

    assert sorted(listing.source_id for listing in listings) == ["a1", "a2"]


async def test_fetch_retries_server_errors():
    source = make_source()
    call_count = [0]

    def mock_get(url, **kwargs):
        if "/rent/" in url and ".json" not in url:
            return make_mock_response(body=NEXT_DATA_HTML)
        elif "/_next/data/" in url and ".json" in url:
            if call_count[0] == 0:
                call_count[0] += 1
                return make_mock_response(status=503)
            else:
                return make_mock_response(json_data=feed_page([
                    feed_item("a1", "קריית ביאליק"),
                ]))
        raise Exception(f"Unexpected URL: {url}")

    session = AsyncMock()
    session.get = mock_get
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    with patch("apt.sources.yad2.aiohttp.ClientSession", return_value=session):
        listings = await source.fetch([Location(city="קריית ביאליק")])

    assert [listing.source_id for listing in listings] == ["a1"]


async def test_fetch_unknown_city_skipped_entirely():
    source = make_source()
    listings = await source.fetch([Location(city="עיר לא ממופה")])
    assert listings == []


async def test_fetch_neighborhood_location_requires_hood_match():
    haifa = KNOWN_CITIES["חיפה"]
    source = make_source()

    def mock_get(url, **kwargs):
        if "/rent/" in url and ".json" not in url:
            return make_mock_response(body=NEXT_DATA_HTML)
        elif "/_next/data/" in url and ".json" in url:
            return make_mock_response(json_data=feed_page([
                feed_item("in-hood", "חיפה", neighborhood="קריית חיים מערבית"),
                feed_item("other-hood", "חיפה", neighborhood="הדר"),
            ]))
        raise Exception(f"Unexpected URL: {url}")

    session = AsyncMock()
    session.get = mock_get
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    with patch("apt.sources.yad2.aiohttp.ClientSession", return_value=session):
        listings = await source.fetch(
            [Location(city="חיפה", neighborhood="קריית חיים מערבית")]
        )

    assert [listing.source_id for listing in listings] == ["in-hood"]


async def test_enrich_failure_returns_listing_unchanged(caplog):
    source = make_source()

    def mock_get(url, **kwargs):
        if "/rent/" in url and ".json" not in url:
            return make_mock_response(body=NEXT_DATA_HTML)
        elif "/_next/data/" in url and ".json" in url:
            return make_mock_response(json_data=feed_page([feed_item("a1", "קריית ביאליק")]))
        raise Exception(f"Unexpected URL: {url}")

    session = AsyncMock()
    session.get = mock_get
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    with patch("apt.sources.yad2.aiohttp.ClientSession", return_value=session):
        listings = await source.fetch([Location(city="קריית ביאליק")])
        enriched = await source.enrich(listings[0])

    assert enriched == listings[0]
