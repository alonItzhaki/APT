from datetime import datetime, timedelta, timezone

from apt.api.session import sign_session, verify_session

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


def test_roundtrip():
    token = sign_session(7, NOW + timedelta(days=30), "secret")
    assert verify_session(token, "secret", NOW) == 7


def test_expired_returns_none():
    token = sign_session(7, NOW - timedelta(seconds=1), "secret")
    assert verify_session(token, "secret", NOW) is None


def test_wrong_secret_or_tampered_returns_none():
    token = sign_session(7, NOW + timedelta(days=30), "secret")
    assert verify_session(token, "other", NOW) is None
    user_id, ts, sig = token.split(".")
    assert verify_session(f"8.{ts}.{sig}", "secret", NOW) is None


def test_malformed_returns_none():
    assert verify_session("garbage", "secret", NOW) is None
    assert verify_session("a.b.c", "secret", NOW) is None
