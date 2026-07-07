import os
from pathlib import Path

from pydantic import BaseModel


class WebConfig(BaseModel):
    db_path: Path
    secret_key: str
    google_client_id: str
    google_client_secret: str
    base_url: str
    bot_username: str
    admin_emails: list[str]
    frontend_dist: Path | None = None


def load_web_config() -> WebConfig:
    admin_emails = [
        email.strip()
        for email in os.getenv("APT_ADMIN_EMAILS", "").split(",")
        if email.strip()
    ]
    frontend_dist = os.getenv("APT_FRONTEND_DIST", "")
    return WebConfig(
        db_path=Path(os.getenv("APT_DB_PATH", "data/apt.db")),
        secret_key=os.getenv("APT_SECRET_KEY", "dev-secret-change-me"),
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        base_url=os.getenv("APT_BASE_URL", "http://localhost:8000").rstrip("/"),
        bot_username=os.getenv("APT_BOT_USERNAME", ""),
        admin_emails=admin_emails,
        frontend_dist=Path(frontend_dist) if frontend_dist else None,
    )
