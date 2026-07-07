from datetime import datetime, timezone

from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


def test_upsert_creates_user(conn):
    repo = UserRepo(conn)
    user = repo.upsert_google_user("g-1", "a@b.com", NOW)
    assert user.id > 0
    assert user.google_sub == "g-1"
    assert user.email == "a@b.com"
    assert user.telegram_chat_id is None


def test_upsert_same_sub_updates_email_keeps_id(conn):
    repo = UserRepo(conn)
    first = repo.upsert_google_user("g-1", "a@b.com", NOW)
    second = repo.upsert_google_user("g-1", "new@b.com", NOW)
    assert second.id == first.id
    assert second.email == "new@b.com"


def test_get_by_google_sub_and_missing(conn):
    repo = UserRepo(conn)
    created = repo.upsert_google_user("g-1", "a@b.com", NOW)
    assert repo.get_by_google_sub("g-1") == created
    assert repo.get_by_google_sub("nope") is None
    assert repo.get(created.id) == created
    assert repo.get(9999) is None


def test_set_and_lookup_telegram_chat(conn):
    repo = UserRepo(conn)
    user = repo.upsert_google_user("g-1", "a@b.com", NOW)
    repo.set_telegram_chat(user.id, 555)
    assert repo.get(user.id).telegram_chat_id == 555
    assert repo.get_by_telegram_chat(555).id == user.id
    repo.set_telegram_chat(user.id, None)
    assert repo.get_by_telegram_chat(555) is None


def test_delete_removes_user(conn):
    repo = UserRepo(conn)
    user = repo.upsert_google_user("g-1", "a@b.com", NOW)
    repo.delete(user.id)
    assert repo.get(user.id) is None
