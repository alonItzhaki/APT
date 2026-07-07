import json
import sqlite3
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from apt.domain.models import AlertFilters, Listing


class UpsertResult(BaseModel):
    is_new: bool
    price_changed: bool = False
    old_price: int | None = None


def _to_bool(value: int | None) -> bool | None:
    return None if value is None else bool(value)


def _row_to_listing(row: sqlite3.Row) -> Listing:
    return Listing(
        source=row["source"],
        source_id=row["source_id"],
        url=row["url"],
        city=row["city"],
        neighborhood=row["neighborhood"],
        street=row["street"],
        price=row["price"],
        rooms=row["rooms"],
        size_sqm=row["size_sqm"],
        floor=row["floor"],
        has_mamad=_to_bool(row["has_mamad"]),
        has_elevator=_to_bool(row["has_elevator"]),
        entry_date=date.fromisoformat(row["entry_date"]) if row["entry_date"] else None,
        tags=json.loads(row["tags"]),
        description=row["description"],
        photo_urls=json.loads(row["photo_urls"]),
    )


def _search_clauses(filters: AlertFilters) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if filters.locations:
        location_parts = []
        for loc in filters.locations:
            if loc.neighborhood is not None:
                location_parts.append("(city = ? AND neighborhood = ?)")
                params.extend([loc.city, loc.neighborhood])
            else:
                location_parts.append("city = ?")
                params.append(loc.city)
        clauses.append("(" + " OR ".join(location_parts) + ")")
    for column, low, high in (
        ("price", filters.min_price, filters.max_price),
        ("rooms", filters.min_rooms, filters.max_rooms),
        ("size_sqm", filters.min_size_sqm, None),
        ("floor", filters.min_floor, filters.max_floor),
    ):
        if low is not None:
            clauses.append(f"{column} >= ?")
            params.append(low)
        if high is not None:
            clauses.append(f"{column} <= ?")
            params.append(high)
    if filters.require_mamad:
        clauses.append("has_mamad = 1")
    if filters.require_elevator:
        clauses.append("has_elevator = 1")
    if filters.entry_by is not None:
        clauses.append("(entry_date IS NULL OR entry_date <= ?)")
        params.append(filters.entry_by.isoformat())
    where = " AND ".join(clauses) if clauses else "1=1"
    return where, params


class ListingRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def upsert(self, listing: Listing, now: datetime) -> UpsertResult:
        # Last-scrape-wins on every field: callers must pass fully-populated
        # listings — a partial one silently nulls previously-known data.
        existing = self._conn.execute(
            "SELECT price FROM listings WHERE id = ?", (listing.id,)
        ).fetchone()
        timestamp = now.isoformat()
        values = (
            listing.url,
            listing.city,
            listing.neighborhood,
            listing.street,
            listing.price,
            listing.rooms,
            listing.size_sqm,
            listing.floor,
            None if listing.has_mamad is None else int(listing.has_mamad),
            None if listing.has_elevator is None else int(listing.has_elevator),
            listing.entry_date.isoformat() if listing.entry_date else None,
            json.dumps(listing.tags, ensure_ascii=False),
            listing.description,
            json.dumps(listing.photo_urls),
        )
        if existing is None:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO listings (
                        id, source, source_id, url, city, neighborhood, street,
                        price, rooms, size_sqm, floor, has_mamad, has_elevator,
                        entry_date, tags, description, photo_urls, first_seen, last_seen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (listing.id, listing.source, listing.source_id) + values + (timestamp, timestamp),
                )
                if listing.price is not None:
                    self._conn.execute(
                        "INSERT INTO price_history (listing_id, price, observed_at) VALUES (?, ?, ?)",
                        (listing.id, listing.price, timestamp),
                    )
            return UpsertResult(is_new=True)

        old_price = existing["price"]
        price_changed = listing.price is not None and listing.price != old_price
        with self._conn:
            self._conn.execute(
                """
                UPDATE listings SET
                    url = ?, city = ?, neighborhood = ?, street = ?,
                    price = ?, rooms = ?, size_sqm = ?, floor = ?,
                    has_mamad = ?, has_elevator = ?, entry_date = ?,
                    tags = ?, description = ?, photo_urls = ?, last_seen = ?
                WHERE id = ?
                """,
                values + (timestamp, listing.id),
            )
            if price_changed:
                self._conn.execute(
                    "INSERT INTO price_history (listing_id, price, observed_at) VALUES (?, ?, ?)",
                    (listing.id, listing.price, timestamp),
                )
        return UpsertResult(
            is_new=False,
            price_changed=price_changed,
            old_price=old_price if price_changed else None,
        )

    def get(self, listing_id: str) -> Listing | None:
        row = self._conn.execute(
            "SELECT * FROM listings WHERE id = ?", (listing_id,)
        ).fetchone()
        return _row_to_listing(row) if row else None

    def search(
        self,
        filters: AlertFilters,
        sort: Literal["newest", "price"] = "newest",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Listing]:
        where, params = _search_clauses(filters)
        orders = {"newest": "first_seen DESC", "price": "price IS NULL, price ASC"}
        if sort not in orders:
            raise ValueError(f"unknown sort: {sort!r}")
        order = orders[sort]
        rows = self._conn.execute(
            f"SELECT * FROM listings WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [_row_to_listing(row) for row in rows]

    def price_history(self, listing_id: str) -> list[tuple[int, str]]:
        rows = self._conn.execute(
            "SELECT price, observed_at FROM price_history WHERE listing_id = ? ORDER BY id",
            (listing_id,),
        ).fetchall()
        return [(row["price"], row["observed_at"]) for row in rows]
