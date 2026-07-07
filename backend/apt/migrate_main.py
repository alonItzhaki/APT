import logging

from apt.api.config import load_web_config
from apt.repo.db import connect, migrate

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config = load_web_config()
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(config.db_path)
    migrate(connection)
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    logger.info("migrations applied (user_version=%s)", version)


if __name__ == "__main__":
    main()
