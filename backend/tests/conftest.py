from datetime import datetime, timezone

import pytest

from apt.api.app import create_app
from apt.api.config import WebConfig
from apt.repo.db import connect, migrate

FIXED_NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn(tmp_path):
    # check_same_thread=False is required because FastAPI's TestClient runs the
    # ASGI app in a background thread while the fixture lives on the test thread.
    connection = connect(tmp_path / "test.db", check_same_thread=False)
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

    # Workaround: httpx 0.28 does not honour Max-Age=0 for cookie deletion, so
    # we manually evict cookies from the jar for every Set-Cookie header that
    # carries Max-Age=0.
    client = TestClient(app)
    original_request = client.request

    def request_with_cookie_cleanup(*args, **kwargs):
        response = original_request(*args, **kwargs)
        for header in response.headers.get_list("set-cookie"):
            if "Max-Age=0" in header or "max-age=0" in header:
                cookie_name = header.split("=")[0].strip()
                if cookie_name in client.cookies:
                    client.cookies.delete(cookie_name)
        return response

    client.request = request_with_cookie_cleanup
    return client
