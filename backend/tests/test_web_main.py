from apt import web_main


def test_load_config_defaults(monkeypatch):
    for var in ("APT_DB_PATH", "APT_SECRET_KEY", "APT_ADMIN_EMAILS", "APT_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    config = web_main.load_config()
    assert str(config.db_path) == "data/apt.db"
    assert config.admin_emails == []
    assert config.base_url == "http://localhost:8000"
