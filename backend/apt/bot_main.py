import logging
import os
import sys
from pathlib import Path

from pydantic import BaseModel

from apt.bot import build_application
from apt.repo.db import connect, migrate

logger = logging.getLogger(__name__)


class BotConfig(BaseModel):
    token: str
    db_path: Path
    site_url: str


def load_config() -> BotConfig:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set")
        sys.exit(1)
    return BotConfig(
        token=token,
        db_path=Path(os.getenv("APT_DB_PATH", "data/apt.db")),
        site_url=os.getenv("APT_SITE_URL", "https://apt.example.com"),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config = load_config()
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(config.db_path)
    migrate(conn)
    application = build_application(config.token, conn, config.site_url)
    logger.info("bot starting (db=%s)", config.db_path)
    application.run_polling()


if __name__ == "__main__":
    main()
