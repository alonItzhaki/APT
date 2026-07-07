from apt.domain.models import Listing
from apt.repo.listings import ListingRepo
from apt.repo.scrape_set import ScrapeSetRepo
from tests.conftest import FIXED_NOW


def seed(conn):
    repo = ListingRepo(conn)
    repo.upsert(Listing(source="yad2", source_id="a1", url="https://e.com/a1",
                        city="חיפה", price=5000, rooms=3.5, has_mamad=True), FIXED_NOW)
    repo.upsert(Listing(source="yad2", source_id="a2", url="https://e.com/a2",
                        city="חיפה", price=7000, rooms=4.0), FIXED_NOW)
    repo.upsert(Listing(source="yad2", source_id="b1", url="https://e.com/b1",
                        city="תל אביב", price=9000), FIXED_NOW)


def test_search_filters_by_city_and_price(client, conn):
    seed(conn)
    payload = client.get("/api/listings", params={"city": "חיפה", "max_price": 6000}).json()
    assert [item["source_id"] for item in payload["listings"]] == ["a1"]


def test_search_requires_city(client):
    assert client.get("/api/listings").status_code == 422


def test_search_logs_location_and_reports_newly_tracked(client, conn):
    seed(conn)
    first = client.get("/api/listings", params={"city": "באר שבע"}).json()
    assert first["newly_tracked"] is True
    assert first["listings"] == []
    locations = ScrapeSetRepo(conn).active_locations(FIXED_NOW)
    assert any(loc.city == "באר שבע" for loc in locations)
    second = client.get("/api/listings", params={"city": "באר שבע"}).json()
    assert second["newly_tracked"] is False


def test_search_clamps_limit_and_offset(client, conn):
    seed(conn)
    payload = client.get(
        "/api/listings", params={"city": "חיפה", "limit": 9999, "offset": -5}
    ).json()
    assert len(payload["listings"]) == 2


def test_search_amenity_and_sort(client, conn):
    seed(conn)
    payload = client.get(
        "/api/listings", params={"city": "חיפה", "require_mamad": "true", "sort": "price"}
    ).json()
    assert [item["source_id"] for item in payload["listings"]] == ["a1"]
