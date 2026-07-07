from fastapi.testclient import TestClient

from apt.api.app import create_app
from tests.conftest import FIXED_NOW


def test_rate_limit_kicks_in(conn, web_config):
    app = create_app(conn, web_config, now_fn=lambda: FIXED_NOW, rate_limit_per_minute=3)
    client = TestClient(app)
    for _ in range(3):
        assert client.get("/api/listings", params={"city": "חיפה"}).status_code == 200
    assert client.get("/api/listings", params={"city": "חיפה"}).status_code == 429
    assert client.get("/healthz").status_code == 200
