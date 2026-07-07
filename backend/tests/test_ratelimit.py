import time

from fastapi.testclient import TestClient

from apt.api.app import create_app
from apt.api.ratelimit import WINDOW_SECONDS, RateLimitMiddleware
from tests.conftest import FIXED_NOW


def test_rate_limit_kicks_in(conn, web_config):
    app = create_app(conn, web_config, now_fn=lambda: FIXED_NOW, rate_limit_per_minute=3)
    client = TestClient(app)
    for _ in range(3):
        assert client.get("/api/listings", params={"city": "חיפה"}).status_code == 200
    assert client.get("/api/listings", params={"city": "חיפה"}).status_code == 429
    assert client.get("/healthz").status_code == 200


def test_stale_ips_evicted():
    middleware = RateLimitMiddleware(app=None, max_requests=5, max_tracked_ips=2)
    now = time.monotonic()
    middleware._hits["1.1.1.1"].append(now - WINDOW_SECONDS - 5)
    middleware._hits["2.2.2.2"].append(now - WINDOW_SECONDS - 5)
    middleware._hits["3.3.3.3"].append(now)
    middleware._sweep(now)
    assert set(middleware._hits) == {"3.3.3.3"}
