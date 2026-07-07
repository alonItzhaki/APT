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
