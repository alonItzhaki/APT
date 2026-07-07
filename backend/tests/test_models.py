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
