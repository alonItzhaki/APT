from datetime import datetime, timedelta, timezone

from apt.domain.models import AlertFilters, Location
from apt.repo.alerts import AlertRepo
from apt.repo.scrape_set import ScrapeSetRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


def make_alert(conn, locations, active=True):
    user_repo = UserRepo(conn)
    user = user_repo.get_by_google_sub("g-1") or user_repo.upsert_google_user("g-1", "a@b.com", NOW)
    repo = AlertRepo(conn)
    alert = repo.create(user.id, "x", AlertFilters(locations=locations), ["telegram"], NOW)
    if not active:
        repo.set_active(alert.id, False)
    return alert


def test_empty_scrape_set(conn):
    assert ScrapeSetRepo(conn).active_locations(NOW) == []


def test_locations_from_active_alerts_only(conn):
    make_alert(conn, [Location(city="חיפה")])
    make_alert(conn, [Location(city="תל אביב")], active=False)
    locations = ScrapeSetRepo(conn).active_locations(NOW)
    assert locations == [Location(city="חיפה")]


def test_recent_searches_included_old_excluded(conn):
    repo = ScrapeSetRepo(conn)
    repo.log_search(Location(city="באר שבע"), NOW - timedelta(days=5))
    repo.log_search(Location(city="אילת"), NOW - timedelta(days=45))
    locations = repo.active_locations(NOW)
    assert Location(city="באר שבע") in locations
    assert Location(city="אילת") not in locations


def test_union_is_deduplicated(conn):
    repo = ScrapeSetRepo(conn)
    make_alert(conn, [Location(city="חיפה", neighborhood="הדר"), Location(city="חיפה")])
    repo.log_search(Location(city="חיפה"), NOW)
    repo.log_search(Location(city="חיפה", neighborhood="הדר"), NOW)
    locations = repo.active_locations(NOW)
    assert len(locations) == 2
    assert set((loc.city, loc.neighborhood) for loc in locations) == {
        ("חיפה", None),
        ("חיפה", "הדר"),
    }
