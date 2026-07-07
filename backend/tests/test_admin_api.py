from datetime import timedelta

from apt.api.session import SESSION_COOKIE, sign_session
from apt.repo.source_state import SourceStateRepo
from apt.repo.users import UserRepo
from tests.conftest import FIXED_NOW


def login(client, conn, web_config, email):
    sub = f"g-{email}"
    user = UserRepo(conn).upsert_google_user(sub, email, FIXED_NOW)
    token = sign_session(user.id, FIXED_NOW + timedelta(days=30), web_config.secret_key)
    client.cookies.set(SESSION_COOKIE, token)
    return user


def test_admin_requires_admin_email(client, conn, web_config):
    assert client.get("/api/admin/health").status_code == 401
    login(client, conn, web_config, "u@example.com")
    assert client.get("/api/admin/health").status_code == 403


def test_admin_health_reports_sources_and_counts(client, conn, web_config):
    SourceStateRepo(conn).record_run("yad2", FIXED_NOW)
    login(client, conn, web_config, "admin@example.com")
    payload = client.get("/api/admin/health").json()
    assert payload["counts"]["users"] == 1
    assert any(source["source"] == "yad2" for source in payload["sources"])


def test_admin_toggles_source(client, conn, web_config):
    login(client, conn, web_config, "admin@example.com")
    payload = client.post("/api/admin/sources/facebook", json={"enabled": False}).json()
    assert payload["enabled"] is False
    assert SourceStateRepo(conn).get("facebook").enabled is False
    assert client.post("/api/admin/sources/craigslist", json={"enabled": False}).status_code == 404
