from apt import scraper_main


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("APT_DB_PATH", raising=False)
    monkeypatch.delenv("APT_SCRAPE_INTERVAL_SECONDS", raising=False)
    config = scraper_main.load_config()
    assert str(config.db_path) == "data/apt.db"
    assert config.interval_seconds == 900


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("APT_DB_PATH", "/tmp/x.db")
    monkeypatch.setenv("APT_SCRAPE_INTERVAL_SECONDS", "60")
    config = scraper_main.load_config()
    assert str(config.db_path) == "/tmp/x.db"
    assert config.interval_seconds == 60
