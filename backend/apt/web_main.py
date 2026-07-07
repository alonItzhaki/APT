import logging
import os
import sys

import uvicorn

from apt.api.app import create_app
from apt.api.config import WebConfig, load_web_config
from apt.repo.db import connect, migrate

logger = logging.getLogger(__name__)


def load_config() -> WebConfig:
    return load_web_config()


def refuse_default_secret(config: WebConfig) -> None:
    if config.base_url.startswith("https://") and config.secret_key == "dev-secret-change-me":
        logger.error("APT_SECRET_KEY is still the default; refusing to serve %s", config.base_url)
        sys.exit(1)


def uvicorn_kwargs() -> dict:
    if os.getenv("APT_BEHIND_PROXY", "").lower() in ("1", "true"):
        return {"proxy_headers": True, "forwarded_allow_ips": "*"}
    return {}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config = load_config()
    refuse_default_secret(config)
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(config.db_path, check_same_thread=False)  # FastAPI runs sync endpoints in a threadpool; sqlite objects cross threads here.
    migrate(conn)
    app = create_app(conn, config)
    port = int(os.getenv("APT_PORT", "8000"))
    logger.info("web api starting on :%d (db=%s)", port, config.db_path)
    uvicorn.run(app, host="0.0.0.0", port=port, **uvicorn_kwargs())


if __name__ == "__main__":
    main()
