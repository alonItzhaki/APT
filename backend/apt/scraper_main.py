import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from apt.cycle import run_cycle
from apt.notify.base import LogNotifier
from apt.repo.db import connect, migrate
from apt.sources.yad2 import Yad2Source

logger = logging.getLogger(__name__)


class ScraperConfig(BaseModel):
    db_path: Path
    interval_seconds: int


def load_config() -> ScraperConfig:
    return ScraperConfig(
        db_path=Path(os.getenv("APT_DB_PATH", "data/apt.db")),
        interval_seconds=int(os.getenv("APT_SCRAPE_INTERVAL_SECONDS", "900")),
    )


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    config = load_config()
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(config.db_path)
    migrate(conn)
    notifier = LogNotifier()
    logger.info("scraper started (db=%s, interval=%ss)", config.db_path, config.interval_seconds)
    while True:
        # A fresh source per cycle re-discovers the build_id, surviving Yad2 redeploys.
        source = Yad2Source()
        try:
            events = await run_cycle(conn, [source], notifier, datetime.now(timezone.utc))
            logger.info("cycle finished: %d match events", len(events))
        except Exception:
            logger.exception("cycle crashed; retrying next interval")
        await asyncio.sleep(config.interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
