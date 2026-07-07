import sqlite3


class StatsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def counts(self) -> dict:
        def count(table: str) -> int:
            return self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        return {"users": count("users"), "alerts": count("alerts"), "listings": count("listings")}
