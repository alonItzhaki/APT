import logging
import os

import uvicorn

from apt.api.app import create_app
from apt.api.config import WebConfig, load_web_config
from apt.repo.db import connect, migrate

logger = logging.getLogger(__name__)


def load_config() -> WebConfig:
    return load_web_config()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config = load_config()
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(config.db_path, check_same_thread=False)  # FastAPI runs sync endpoints in a threadpool; sqlite objects cross threads here.
    migrate(conn)
    app = create_app(conn, config)
    port = int(os.getenv("APT_PORT", "8000"))
    logger.info("web api starting on :%d (db=%s)", port, config.db_path)
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
