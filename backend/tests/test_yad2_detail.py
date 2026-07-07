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
