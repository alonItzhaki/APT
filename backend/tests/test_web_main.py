import pytest

from apt import web_main
from apt.api.config import WebConfig


def test_load_config_defaults(monkeypatch):
    for var in ("APT_DB_PATH", "APT_SECRET_KEY", "APT_ADMIN_EMAILS", "APT_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    config = web_main.load_config()
    assert str(config.db_path) == "data/apt.db"
    assert config.admin_emails == []
    assert config.base_url == "http://localhost:8000"


def test_app_serves_db_requests_across_threads(tmp_path, web_config):
    from fastapi.testclient import TestClient

    from apt.api.app import create_app
    from apt.repo.db import connect, migrate

    conn = connect(tmp_path / "threaded.db", check_same_thread=False)
    migrate(conn)
    app = create_app(conn, web_config)
    client = TestClient(app)
    assert client.get("/api/listings", params={"city": "חיפה"}).status_code == 200


def make_config(**overrides):
    base = dict(
        db_path="data/apt.db", secret_key="dev-secret-change-me",
        google_client_id="", google_client_secret="",
        base_url="https://apt.example.com", bot_username="", admin_emails=[],
    )
    base.update(overrides)
    return WebConfig(**base)


def test_refuses_default_secret_on_https():
    with pytest.raises(SystemExit):
        web_main.refuse_default_secret(make_config())


def test_allows_default_secret_on_http_dev():
    web_main.refuse_default_secret(make_config(base_url="http://localhost:8000"))


def test_allows_real_secret_on_https():
    web_main.refuse_default_secret(make_config(secret_key="s3cret"))


def test_uvicorn_kwargs_behind_proxy(monkeypatch):
    monkeypatch.setenv("APT_BEHIND_PROXY", "1")
    assert web_main.uvicorn_kwargs() == {"proxy_headers": True, "forwarded_allow_ips": "*"}
    monkeypatch.delenv("APT_BEHIND_PROXY")
    assert web_main.uvicorn_kwargs() == {}
