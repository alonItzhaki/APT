import sqlite3
from datetime import datetime

from pydantic import BaseModel


class SourceState(BaseModel):
    source: str
    enabled: bool = True
    last_run: str | None = None
    last_success: str | None = None
    last_error: str | None = None


def _row_to_state(row: sqlite3.Row) -> SourceState:
    return SourceState(
        source=row["source"],
        enabled=bool(row["enabled"]),
        last_run=row["last_run"],
        last_success=row["last_success"],
        last_error=row["last_error"],
    )


class SourceStateRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def _ensure_row(self, source: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO source_state (source) VALUES (?)", (source,)
        )

    def get(self, source: str) -> SourceState:
        row = self._conn.execute(
            "SELECT * FROM source_state WHERE source = ?", (source,)
        ).fetchone()
        return _row_to_state(row) if row else SourceState(source=source)

    def set_enabled(self, source: str, enabled: bool) -> None:
        with self._conn:
            self._ensure_row(source)
            self._conn.execute(
                "UPDATE source_state SET enabled = ? WHERE source = ?",
                (int(enabled), source),
            )

    def record_run(self, source: str, now: datetime, error: str | None = None) -> None:
        timestamp = now.isoformat()
        with self._conn:
            self._ensure_row(source)
            if error is None:
                self._conn.execute(
                    """
                    UPDATE source_state
                    SET last_run = ?, last_success = ?, last_error = NULL
                    WHERE source = ?
                    """,
                    (timestamp, timestamp, source),
                )
            else:
                self._conn.execute(
                    "UPDATE source_state SET last_run = ?, last_error = ? WHERE source = ?",
                    (timestamp, error, source),
                )

    def all(self) -> list[SourceState]:
        rows = self._conn.execute("SELECT * FROM source_state ORDER BY source").fetchall()
        return [_row_to_state(row) for row in rows]
