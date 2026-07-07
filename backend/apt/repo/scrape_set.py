import sqlite3
from datetime import datetime, timedelta

from apt.domain.models import Location
from apt.repo.alerts import AlertRepo


class ScrapeSetRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def log_search(self, location: Location, now: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO search_log (city, neighborhood, searched_at) VALUES (?, ?, ?)",
                (location.city, location.neighborhood, now.isoformat()),
            )

    def active_locations(self, now: datetime, max_age_days: int = 30) -> list[Location]:
        seen: set[tuple[str, str | None]] = set()
        result: list[Location] = []

        def add(location: Location) -> None:
            key = (location.city, location.neighborhood)
            if key not in seen:
                seen.add(key)
                result.append(location)

        for alert in AlertRepo(self._conn).list_active():
            for location in alert.filters.locations:
                add(location)

        cutoff = (now - timedelta(days=max_age_days)).isoformat()
        rows = self._conn.execute(
            "SELECT DISTINCT city, neighborhood FROM search_log WHERE searched_at >= ?",
            (cutoff,),
        ).fetchall()
        for row in rows:
            add(Location(city=row["city"], neighborhood=row["neighborhood"]))
        return result
