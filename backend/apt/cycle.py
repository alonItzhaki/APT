import logging
import sqlite3
from datetime import datetime

from apt.domain.events import MatchEvent
from apt.domain.matching import listing_matches
from apt.domain.models import Listing
from apt.notify.base import Notifier
from apt.repo.alerts import AlertRepo
from apt.repo.listings import ListingRepo
from apt.repo.scrape_set import ScrapeSetRepo
from apt.repo.source_state import SourceStateRepo
from apt.sources.base import Source

logger = logging.getLogger(__name__)


def merge_preserving_enrichment(existing: Listing | None, incoming: Listing) -> Listing:
    """Feed items lack detail-only fields; keep known values instead of erasing them."""
    if existing is None:
        return incoming
    updates: dict = {}
    if not incoming.description and existing.description:
        updates["description"] = existing.description
    if incoming.has_mamad is None and existing.has_mamad is not None:
        updates["has_mamad"] = existing.has_mamad
    if incoming.has_elevator is None and existing.has_elevator is not None:
        updates["has_elevator"] = existing.has_elevator
    if incoming.entry_date is None and existing.entry_date is not None:
        updates["entry_date"] = existing.entry_date
    return incoming.model_copy(update=updates) if updates else incoming


async def run_cycle(
    conn: sqlite3.Connection,
    sources: list[Source],
    notifier: Notifier,
    now: datetime,
) -> list[MatchEvent]:
    locations = ScrapeSetRepo(conn).active_locations(now)
    if not locations:
        logger.info("cycle: no active locations - nothing to scrape")
        return []

    listings_repo = ListingRepo(conn)
    state_repo = SourceStateRepo(conn)
    alerts = AlertRepo(conn).list_active()
    events: list[MatchEvent] = []

    for source in sources:
        if not state_repo.get(source.name).enabled:
            logger.info("cycle: source %s disabled - skipped", source.name)
            continue
        try:
            fetched = await source.fetch(locations)
        except Exception as exc:
            logger.error("cycle: source %s failed: %s", source.name, exc)
            state_repo.record_run(source.name, now, error=str(exc))
            continue

        for listing in fetched:
            merged = merge_preserving_enrichment(listings_repo.get(listing.id), listing)
            result = listings_repo.upsert(merged, now)
            final = merged
            if result.is_new:
                final = await source.enrich(merged)
                if final != merged:
                    listings_repo.upsert(final, now)

            if result.is_new:
                kind, old_price = "new", None
            elif (
                result.price_changed
                and result.old_price is not None
                and final.price is not None
                and final.price < result.old_price
            ):
                kind, old_price = "price_drop", result.old_price
            else:
                continue

            for alert in alerts:
                if listing_matches(final, alert.filters):
                    events.append(
                        MatchEvent(kind=kind, listing=final, alert=alert, old_price=old_price)
                    )

        state_repo.record_run(source.name, now)
        logger.info("cycle: source %s returned %d listings", source.name, len(fetched))

    for event in events:
        await notifier.send(event)
    return events
