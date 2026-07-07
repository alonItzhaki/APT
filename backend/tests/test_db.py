import sqlite3

import pytest

import apt.repo.db
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


def test_migrate_atomicity(tmp_path, monkeypatch):
    # Start with a freshly migrated v1 database.
    connection = connect(tmp_path / "atomic.db")
    migrate(connection)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 1

    original_migrations = list(apt.repo.db.MIGRATIONS)

    # Patch MIGRATIONS with a broken v2: first statement is valid DDL,
    # second statement has a syntax error so the whole script must roll back.
    bad_v2 = "CREATE TABLE extra_ok (id INTEGER PRIMARY KEY); CREATE TABLE broken (syntax error"
    monkeypatch.setattr(apt.repo.db, "MIGRATIONS", original_migrations + [bad_v2])

    with pytest.raises(sqlite3.OperationalError):
        migrate(connection)

    # The migration must have been fully rolled back: user_version unchanged
    # and the partial table must not exist.
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "extra_ok" not in tables

    # A corrected v2 migration must succeed on the same connection.
    good_v2 = "CREATE TABLE extra_ok (id INTEGER PRIMARY KEY);"
    monkeypatch.setattr(apt.repo.db, "MIGRATIONS", original_migrations + [good_v2])
    migrate(connection)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    tables_after = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "extra_ok" in tables_after
