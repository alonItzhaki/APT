import sqlite3
from datetime import datetime


class NotificationRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def claim(self, alert_id: int, listing_id: str, channel: str, now: datetime) -> bool:
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO sent_notifications (alert_id, listing_id, channel, sent_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (alert_id, listing_id, channel, now.isoformat()),
                )
            return True
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed" in str(exc):
                return False
            raise

    def release(self, alert_id: int, listing_id: str, channel: str) -> None:
        with self._conn:
            self._conn.execute(
                """
                DELETE FROM sent_notifications
                WHERE alert_id = ? AND listing_id = ? AND channel = ?
                """,
                (alert_id, listing_id, channel),
            )
