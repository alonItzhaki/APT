from datetime import datetime, timedelta, timezone

from apt.repo.link_tokens import LinkTokenRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


def make_user(conn):
    return UserRepo(conn).upsert_google_user("g-1", "a@b.com", NOW)


def test_consume_valid_token_once(conn):
    user = make_user(conn)
    repo = LinkTokenRepo(conn)
    repo.create("tok-1", user.id, NOW)
    assert repo.consume("tok-1", NOW + timedelta(minutes=5)) == user.id
    assert repo.consume("tok-1", NOW + timedelta(minutes=6)) is None


def test_consume_unknown_token(conn):
    assert LinkTokenRepo(conn).consume("nope", NOW) is None


def test_consume_expired_token(conn):
    user = make_user(conn)
    repo = LinkTokenRepo(conn)
    repo.create("tok-1", user.id, NOW)
    assert repo.consume("tok-1", NOW + timedelta(minutes=16)) is None
