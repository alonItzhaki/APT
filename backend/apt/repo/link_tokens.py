import sqlite3
from datetime import datetime, timedelta


class LinkTokenRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, token: str, user_id: int, now: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO link_tokens (token, user_id, created_at) VALUES (?, ?, ?)",
                (token, user_id, now.isoformat()),
            )

    def consume(self, token: str, now: datetime, max_age_minutes: int = 15) -> int | None:
        row = self._conn.execute(
            "SELECT user_id, created_at, used_at FROM link_tokens WHERE token = ?",
            (token,),
        ).fetchone()
        if row is None or row["used_at"] is not None:
            return None
        created = datetime.fromisoformat(row["created_at"])
        if now - created > timedelta(minutes=max_age_minutes):
            return None
        with self._conn:
            self._conn.execute(
                "UPDATE link_tokens SET used_at = ? WHERE token = ?",
                (now.isoformat(), token),
            )
        return row["user_id"]
