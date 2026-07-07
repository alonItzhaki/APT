import sqlite3
from pathlib import Path

MIGRATIONS: list[str] = [
    # v1: initial schema
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        google_sub TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL,
        telegram_chat_id INTEGER,
        created_at TEXT NOT NULL
    );

    CREATE TABLE alerts (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        filters TEXT NOT NULL,
        channels TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE listings (
        id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        source_id TEXT NOT NULL,
        url TEXT NOT NULL,
        city TEXT NOT NULL,
        neighborhood TEXT,
        street TEXT,
        price INTEGER,
        rooms REAL,
        size_sqm INTEGER,
        floor INTEGER,
        has_mamad INTEGER,
        has_elevator INTEGER,
        entry_date TEXT,
        tags TEXT NOT NULL DEFAULT '[]',
        description TEXT NOT NULL DEFAULT '',
        photo_urls TEXT NOT NULL DEFAULT '[]',
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        UNIQUE (source, source_id)
    );
    CREATE INDEX idx_listings_city ON listings(city);
    CREATE INDEX idx_listings_first_seen ON listings(first_seen);

    CREATE TABLE price_history (
        id INTEGER PRIMARY KEY,
        listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
        price INTEGER NOT NULL,
        observed_at TEXT NOT NULL
    );

    CREATE TABLE sent_notifications (
        alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
        listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
        channel TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        PRIMARY KEY (alert_id, listing_id, channel)
    );

    CREATE TABLE source_state (
        source TEXT PRIMARY KEY,
        enabled INTEGER NOT NULL DEFAULT 1,
        last_run TEXT,
        last_success TEXT,
        last_error TEXT
    );

    CREATE TABLE search_log (
        id INTEGER PRIMARY KEY,
        city TEXT NOT NULL,
        neighborhood TEXT,
        searched_at TEXT NOT NULL
    );
    """,
]


def connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    current = connection.execute("PRAGMA user_version").fetchone()[0]
    for version, script in enumerate(MIGRATIONS[current:], start=current + 1):
        with connection:
            connection.executescript(script)
            connection.execute(f"PRAGMA user_version = {version}")
