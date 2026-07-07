from apt.repo.db import connect, migrate

EXPECTED_TABLES = {
    "users",
    "alerts",
    "listings",
    "price_history",
    "sent_notifications",
    "source_state",
    "search_log",
}


def test_wal_mode_enabled(tmp_path):
    connection = connect(tmp_path / "wal.db")
    mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


def test_foreign_keys_enabled(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migrate_creates_all_tables(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {row["name"] for row in rows}
    assert EXPECTED_TABLES <= names


def test_migrate_is_idempotent(tmp_path):
    connection = connect(tmp_path / "idem.db")
    migrate(connection)
    migrate(connection)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
