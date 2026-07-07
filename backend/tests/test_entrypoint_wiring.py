from apt import bot_main, scraper_main
from apt.notify.base import LogNotifier
from apt.notify.notifier import ChannelNotifier
from apt.repo.db import connect, migrate


def make_conn(tmp_path):
    conn = connect(tmp_path / "wiring.db")
    migrate(conn)
    return conn


def test_build_notifier_defaults_to_log(monkeypatch, tmp_path):
    for var in ("TELEGRAM_BOT_TOKEN", "BREVO_API_KEY", "APT_EMAIL_FROM"):
        monkeypatch.delenv(var, raising=False)
    assert isinstance(scraper_main.build_notifier(make_conn(tmp_path)), LogNotifier)


def test_build_notifier_with_telegram(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    notifier = scraper_main.build_notifier(make_conn(tmp_path))
    assert isinstance(notifier, ChannelNotifier)
    assert set(notifier._channels) == {"telegram"}


def test_build_notifier_with_both_channels(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("APT_EMAIL_FROM", "apt@example.com")
    notifier = scraper_main.build_notifier(make_conn(tmp_path))
    assert set(notifier._channels) == {"telegram", "email"}


def test_bot_config_requires_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("APT_DB_PATH", "/tmp/x.db")
    try:
        bot_main.load_config()
        raised = False
    except SystemExit:
        raised = True
    assert raised


def test_bot_config_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("APT_DB_PATH", "/tmp/x.db")
    monkeypatch.setenv("APT_SITE_URL", "https://apt.co.il")
    config = bot_main.load_config()
    assert config.token == "123:abc"
    assert config.site_url == "https://apt.co.il"
