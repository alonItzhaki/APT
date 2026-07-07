from datetime import datetime, timezone

import pytest

from apt.domain.models import AlertFilters, Listing
from apt.repo.alerts import AlertRepo
from apt.repo.listings import ListingRepo
from apt.repo.notifications import NotificationRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def ids(conn):
    user = UserRepo(conn).upsert_google_user("g-1", "a@b.com", NOW)
    alert = AlertRepo(conn).create(user.id, "x", AlertFilters(), ["telegram"], NOW)
    listing = Listing(source="yad2", source_id="a1", url="https://e.com/a1", city="חיפה")
    ListingRepo(conn).upsert(listing, NOW)
    return alert.id, listing.id


def test_first_claim_wins_second_loses(conn, ids):
    repo = NotificationRepo(conn)
    alert_id, listing_id = ids
    assert repo.claim(alert_id, listing_id, "telegram", NOW) is True
    assert repo.claim(alert_id, listing_id, "telegram", NOW) is False


def test_different_channel_is_a_separate_claim(conn, ids):
    repo = NotificationRepo(conn)
    alert_id, listing_id = ids
    assert repo.claim(alert_id, listing_id, "telegram", NOW) is True
    assert repo.claim(alert_id, listing_id, "email", NOW) is True


def test_release_allows_reclaim(conn, ids):
    repo = NotificationRepo(conn)
    alert_id, listing_id = ids
    assert repo.claim(alert_id, listing_id, "telegram", NOW) is True
    repo.release(alert_id, listing_id, "telegram")
    assert repo.claim(alert_id, listing_id, "telegram", NOW) is True
