import pytest

from apt import web_main


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
