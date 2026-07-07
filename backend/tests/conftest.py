from datetime import datetime, timezone

import pytest

from apt.api.app import create_app
from apt.api.config import WebConfig
from apt.repo.db import connect, migrate

FIXED_NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def web_config(tmp_path):
    return WebConfig(
        db_path=tmp_path / "api.db",
        secret_key="test-secret",
        google_client_id="cid",
        google_client_secret="csec",
        base_url="http://testserver",
        bot_username="apt_test_bot",
        admin_emails=["admin@example.com"],
        frontend_dist=None,
    )


@pytest.fixture
def client(conn, web_config):
    from fastapi.testclient import TestClient

    app = create_app(conn, web_config, now_fn=lambda: FIXED_NOW)
    return TestClient(app)
