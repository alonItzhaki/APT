from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from apt.api.session import SESSION_COOKIE, sign_session
from apt.repo.users import UserRepo
from tests.conftest import FIXED_NOW


def make_google_session(token_status=200, userinfo_status=200, email_verified=True):
    def json_response(status, payload):
        response = MagicMock()
        response.status = status
        response.json = AsyncMock(return_value=payload)
        response.text = AsyncMock(return_value=str(payload))
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=response)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    session = MagicMock()
    session.post = MagicMock(return_value=json_response(token_status, {"access_token": "at-1"}))
    session.get = MagicMock(return_value=json_response(
        userinfo_status,
        {"sub": "g-123", "email": "u@example.com", "email_verified": email_verified},
    ))
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    return session_ctx, session


def session_cookie_for(conn, web_config, email="u@example.com", sub="g-1"):
    user = UserRepo(conn).upsert_google_user(sub, email, FIXED_NOW)
    return user, sign_session(user.id, FIXED_NOW + timedelta(days=30), web_config.secret_key)


def test_login_redirects_to_google_with_state(client):
    response = client.get("/api/auth/login", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "state=" in location and "client_id=cid" in location
    assert "apt_oauth_state" in response.cookies


def test_callback_rejects_bad_state(client):
    client.cookies.set("apt_oauth_state", "expected")
    response = client.get("/api/auth/callback?code=c&state=wrong", follow_redirects=False)
    assert response.status_code == 400


def test_callback_rejects_missing_state_cookie(client):
    # No apt_oauth_state cookie present — each test gets a fresh client fixture.
    response = client.get("/api/auth/callback?code=c&state=whatever", follow_redirects=False)
    assert response.status_code == 400


def test_callback_creates_user_and_session(client, conn):
    session_ctx, _ = make_google_session()
    client.cookies.set("apt_oauth_state", "st-1")
    with patch("apt.api.auth.aiohttp.ClientSession", return_value=session_ctx):
        response = client.get("/api/auth/callback?code=c&state=st-1", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/"
    assert SESSION_COOKIE in response.cookies
    assert UserRepo(conn).get_by_google_sub("g-123").email == "u@example.com"


def test_callback_google_error_returns_502(client):
    session_ctx, _ = make_google_session(token_status=500)
    client.cookies.set("apt_oauth_state", "st-1")
    with patch("apt.api.auth.aiohttp.ClientSession", return_value=session_ctx):
        response = client.get("/api/auth/callback?code=c&state=st-1", follow_redirects=False)
    assert response.status_code == 502


def test_callback_rejects_unverified_email(client):
    session_ctx, _ = make_google_session(email_verified=False)
    client.cookies.set("apt_oauth_state", "st-1")
    with patch("apt.api.auth.aiohttp.ClientSession", return_value=session_ctx):
        response = client.get("/api/auth/callback?code=c&state=st-1", follow_redirects=False)
    assert response.status_code == 403


def test_me_requires_auth(client):
    assert client.get("/api/me").status_code == 401


def test_me_returns_user(client, conn, web_config):
    user, cookie = session_cookie_for(conn, web_config, email="admin@example.com")
    client.cookies.set(SESSION_COOKIE, cookie)
    payload = client.get("/api/me").json()
    assert payload == {"id": user.id, "email": "admin@example.com", "telegram_linked": False, "is_admin": True}


def test_logout_clears_cookie(client, conn, web_config):
    _, cookie = session_cookie_for(conn, web_config)
    client.cookies.set(SESSION_COOKIE, cookie)
    response = client.post("/api/auth/logout")
    assert response.json() == {"ok": True}
    assert client.get("/api/me").status_code == 401
