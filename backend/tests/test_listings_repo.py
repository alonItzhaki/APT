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
