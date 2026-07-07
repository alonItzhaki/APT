"""Pure alert-matching rules.

Semantics:
- Empty filter locations match any location; otherwise the listing must match
  at least one filter location (city equal; neighborhood equal too when the
  filter location sets one).
- Numeric bounds are inclusive; a listing with an unknown (None) value fails
  any bound set on that field — we never notify on unknown data.
- require_mamad / require_elevator match only an explicit True.
- entry_by: a missing listing entry_date means "immediate" and matches.
"""

from apt.domain.models import AlertFilters, Listing


def _matches_location(listing: Listing, filters: AlertFilters) -> bool:
    if not filters.locations:
        return True
    for loc in filters.locations:
        if listing.city != loc.city:
            continue
        if loc.neighborhood is not None and listing.neighborhood != loc.neighborhood:
            continue
        return True
    return False


def _within(value: float | None, low: float | None, high: float | None) -> bool:
    if low is None and high is None:
        return True
    if value is None:
        return False
    if low is not None and value < low:
        return False
    if high is not None and value > high:
        return False
    return True


def listing_matches(listing: Listing, filters: AlertFilters) -> bool:
    if not _matches_location(listing, filters):
        return False
    if not _within(listing.price, filters.min_price, filters.max_price):
        return False
    if not _within(listing.rooms, filters.min_rooms, filters.max_rooms):
        return False
    if not _within(listing.size_sqm, filters.min_size_sqm, None):
        return False
    if not _within(listing.floor, filters.min_floor, filters.max_floor):
        return False
    if filters.require_mamad and listing.has_mamad is not True:
        return False
    if filters.require_elevator and listing.has_elevator is not True:
        return False
    if filters.entry_by is not None and listing.entry_date is not None:
        if listing.entry_date > filters.entry_by:
            return False
    return True
