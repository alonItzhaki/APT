import json
import sqlite3
from datetime import datetime

from apt.domain.models import Alert, AlertFilters


def _row_to_alert(row: sqlite3.Row) -> Alert:
    return Alert(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        filters=AlertFilters.model_validate_json(row["filters"]),
        channels=json.loads(row["channels"]),
        active=bool(row["active"]),
    )


class AlertRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(
        self,
        user_id: int,
        name: str,
        filters: AlertFilters,
        channels: list[str],
        now: datetime,
    ) -> Alert:
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO alerts (user_id, name, filters, channels, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, name, filters.model_dump_json(), json.dumps(channels), now.isoformat()),
            )
        return self.get(cursor.lastrowid)

    def get(self, alert_id: int) -> Alert | None:
        row = self._conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        return _row_to_alert(row) if row else None

    def list_for_user(self, user_id: int) -> list[Alert]:
        rows = self._conn.execute(
            "SELECT * FROM alerts WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
        return [_row_to_alert(row) for row in rows]

    def list_active(self) -> list[Alert]:
        rows = self._conn.execute(
            "SELECT * FROM alerts WHERE active = 1 ORDER BY id"
        ).fetchall()
        return [_row_to_alert(row) for row in rows]

    def update(
        self,
        alert_id: int,
        name: str,
        filters: AlertFilters,
        channels: list[str],
    ) -> Alert | None:
        with self._conn:
            self._conn.execute(
                "UPDATE alerts SET name = ?, filters = ?, channels = ? WHERE id = ?",
                (name, filters.model_dump_json(), json.dumps(channels), alert_id),
            )
        return self.get(alert_id)

    def set_active(self, alert_id: int, active: bool) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE alerts SET active = ? WHERE id = ?", (int(active), alert_id)
            )

    def delete(self, alert_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
