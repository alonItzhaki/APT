import sqlite3
from datetime import datetime, timezone
from typing import Callable

from fastapi import FastAPI

from apt.api import account, alerts, auth, listings
from apt.api.config import WebConfig


def create_app(
    conn: sqlite3.Connection,
    config: WebConfig,
    now_fn: Callable[[], datetime] | None = None,
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

    return app
