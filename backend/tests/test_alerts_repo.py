from datetime import datetime, timezone

import pytest

from apt.domain.models import AlertFilters, Location
from apt.repo.alerts import AlertRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def user(conn):
    return UserRepo(conn).upsert_google_user("g-1", "a@b.com", NOW)


def make_filters():
    return AlertFilters(locations=[Location(city="חיפה")], max_price=6000, min_rooms=3.0)


def test_create_and_get_roundtrip(conn, user):
    repo = AlertRepo(conn)
    alert = repo.create(user.id, "3 חדרים בחיפה", make_filters(), ["telegram"], NOW)
    assert alert.id > 0
    assert alert.active is True
    fetched = repo.get(alert.id)
    assert fetched == alert
    assert fetched.filters.max_price == 6000
    assert fetched.filters.locations[0].city == "חיפה"


def test_list_for_user_only_their_alerts(conn, user):
    repo = AlertRepo(conn)
    other = UserRepo(conn).upsert_google_user("g-2", "c@d.com", NOW)
    mine = repo.create(user.id, "mine", make_filters(), ["telegram"], NOW)
    repo.create(other.id, "theirs", make_filters(), ["email"], NOW)
    assert [a.id for a in repo.list_for_user(user.id)] == [mine.id]


def test_list_active_excludes_paused(conn, user):
    repo = AlertRepo(conn)
    active = repo.create(user.id, "on", make_filters(), ["telegram"], NOW)
    paused = repo.create(user.id, "off", make_filters(), ["telegram"], NOW)
    repo.set_active(paused.id, False)
    assert [a.id for a in repo.list_active()] == [active.id]
    assert repo.get(paused.id).active is False


def test_update_changes_fields(conn, user):
    repo = AlertRepo(conn)
    alert = repo.create(user.id, "old", make_filters(), ["telegram"], NOW)
    new_filters = AlertFilters(locations=[Location(city="תל אביב")], max_price=8000)
    updated = repo.update(alert.id, "new", new_filters, ["telegram", "email"])
    assert updated.name == "new"
    assert updated.filters.max_price == 8000
    assert updated.channels == ["telegram", "email"]
    assert repo.update(9999, "x", new_filters, ["email"]) is None


def test_delete_and_user_cascade(conn, user):
    repo = AlertRepo(conn)
    alert = repo.create(user.id, "x", make_filters(), ["telegram"], NOW)
    repo.delete(alert.id)
    assert repo.get(alert.id) is None
    survivor = repo.create(user.id, "y", make_filters(), ["telegram"], NOW)
    UserRepo(conn).delete(user.id)
    assert repo.get(survivor.id) is None
