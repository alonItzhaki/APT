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
