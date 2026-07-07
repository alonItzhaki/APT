from datetime import datetime, timezone

import pytest
import sqlite3

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
    assert repo.claim(alert_id, listing_id, "telegram", "new", 0, NOW) is True
    assert repo.claim(alert_id, listing_id, "telegram", "new", 0, NOW) is False


def test_different_channel_kind_or_price_is_a_separate_claim(conn, ids):
    repo = NotificationRepo(conn)
    alert_id, listing_id = ids
    assert repo.claim(alert_id, listing_id, "telegram", "new", 0, NOW) is True
    assert repo.claim(alert_id, listing_id, "email", "new", 0, NOW) is True
    assert repo.claim(alert_id, listing_id, "telegram", "price_drop", 4500, NOW) is True
    assert repo.claim(alert_id, listing_id, "telegram", "price_drop", 4500, NOW) is False
    assert repo.claim(alert_id, listing_id, "telegram", "price_drop", 4200, NOW) is True


def test_release_allows_reclaim(conn, ids):
    repo = NotificationRepo(conn)
    alert_id, listing_id = ids
    assert repo.claim(alert_id, listing_id, "telegram", "new", 0, NOW) is True
    repo.release(alert_id, listing_id, "telegram", "new", 0)
    assert repo.claim(alert_id, listing_id, "telegram", "new", 0, NOW) is True


def test_claim_with_unknown_alert_raises(conn, ids):
    repo = NotificationRepo(conn)
    _, listing_id = ids
    with pytest.raises(sqlite3.IntegrityError):
        repo.claim(999999, listing_id, "telegram", "new", 0, NOW)
