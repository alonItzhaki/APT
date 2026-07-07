import sqlite3
from datetime import datetime, timezone
from typing import Callable

from fastapi import FastAPI

from apt.api import account, alerts, auth, listings, admin
from apt.api.config import WebConfig
from apt.api.ratelimit import RateLimitMiddleware


def create_app(
    conn: sqlite3.Connection,
    config: WebConfig,
    now_fn: Callable[[], datetime] | None = None,
    rate_limit_per_minute: int = 120,
) -> FastAPI:
    app = FastAPI(title="APT API")
    app.state.conn = conn
    app.state.config = config
    app.state.now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    app.include_router(account.router)
    app.include_router(alerts.router)
    app.include_router(auth.router)
    app.include_router(listings.router)
    app.include_router(admin.router)

    app.add_middleware(RateLimitMiddleware, max_requests=rate_limit_per_minute)

    if config.frontend_dist is not None and config.frontend_dist.is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=config.frontend_dist, html=True), name="spa")

    return app
