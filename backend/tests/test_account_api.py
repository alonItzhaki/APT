from datetime import timedelta

from apt.api.session import SESSION_COOKIE, sign_session
from apt.repo.link_tokens import LinkTokenRepo
from apt.repo.users import UserRepo
from tests.conftest import FIXED_NOW


def login(client, conn, web_config):
    user = UserRepo(conn).upsert_google_user("g-1", "u@example.com", FIXED_NOW)
    token = sign_session(user.id, FIXED_NOW + timedelta(days=30), web_config.secret_key)
    client.cookies.set(SESSION_COOKIE, token)
    return user


def test_link_requires_auth(client):
    assert client.post("/api/telegram/link").status_code == 401


def test_link_mints_consumable_token(client, conn, web_config):
    user = login(client, conn, web_config)
    payload = client.post("/api/telegram/link").json()
    assert payload["expires_minutes"] == 15
    prefix = "https://t.me/apt_test_bot?start="
    assert payload["link"].startswith(prefix)
    token = payload["link"].removeprefix(prefix)
    assert 1 <= len(token) <= 64
    assert LinkTokenRepo(conn).consume(token, FIXED_NOW) == user.id


def test_delete_me_removes_user_and_session(client, conn, web_config):
    user = login(client, conn, web_config)
    response = client.delete("/api/me")
    assert response.json() == {"ok": True}
    assert UserRepo(conn).get(user.id) is None
    assert client.get("/api/me").status_code == 401
