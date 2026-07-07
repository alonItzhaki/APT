import sqlite3
from datetime import datetime

from apt.domain.models import User


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        google_sub=row["google_sub"],
        email=row["email"],
        telegram_chat_id=row["telegram_chat_id"],
    )


class UserRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def upsert_google_user(self, google_sub: str, email: str, now: datetime) -> User:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO users (google_sub, email, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT (google_sub) DO UPDATE SET email = excluded.email
                """,
                (google_sub, email, now.isoformat()),
            )
        return self.get_by_google_sub(google_sub)

    def get(self, user_id: int) -> User | None:
        row = self._conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row else None

    def get_by_google_sub(self, google_sub: str) -> User | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE google_sub = ?", (google_sub,)
        ).fetchone()
        return _row_to_user(row) if row else None

    def get_by_telegram_chat(self, chat_id: int) -> User | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE telegram_chat_id = ?", (chat_id,)
        ).fetchone()
        return _row_to_user(row) if row else None

    def set_telegram_chat(self, user_id: int, chat_id: int | None) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE users SET telegram_chat_id = ? WHERE id = ?", (chat_id, user_id)
            )

    def delete(self, user_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
