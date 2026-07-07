from datetime import datetime, timezone

import pytest

from apt.api.app import create_app
from apt.api.config import WebConfig
from apt.repo.db import connect, migrate

FIXED_NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn(tmp_path):
    # Use check_same_thread=False to allow FastAPI TestClient to access db from different thread
    import sqlite3
    connection = sqlite3.connect(tmp_path / "test.db", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
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

    # Wrap TestClient to handle cookie deletion properly since httpx doesn't handle Max-Age=0 well
    client = TestClient(app)
    original_request = client.request

    def request_with_cookie_cleanup(*args, **kwargs):
        response = original_request(*args, **kwargs)
        # Check if response has Set-Cookie headers with Max-Age=0 and remove from cookies jar
        set_cookie = response.headers.get('set-cookie', '')
        if 'Max-Age=0' in set_cookie or 'max-age=0' in set_cookie:
            # Extract cookie name from Set-Cookie header
            if '=' in set_cookie:
                cookie_name = set_cookie.split('=')[0].strip()
                if cookie_name in client.cookies:
                    client.cookies.delete(cookie_name)
        return response

    client.request = request_with_cookie_cleanup
    return client
