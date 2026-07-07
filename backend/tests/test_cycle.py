from datetime import datetime, timedelta, timezone

import pytest

from apt.cycle import merge_preserving_enrichment, run_cycle
from apt.domain.models import AlertFilters, Listing, Location
from apt.notify.base import LogNotifier
from apt.repo.alerts import AlertRepo
from apt.repo.listings import ListingRepo
from apt.repo.source_state import SourceStateRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(minutes=15)


class FakeSource:
    def __init__(self, name="yad2", listings=None, error=None, enrich_description=None):
        self.name = name
        self.listings = listings or []
        self.error = error
        self.enrich_description = enrich_description
        self.fetch_calls = 0
        self.enriched_tokens = []

    async def fetch(self, locations):
        self.fetch_calls += 1
        if self.error:
            raise self.error
        return list(self.listings)

    async def enrich(self, listing):
        self.enriched_tokens.append(listing.source_id)
        if self.enrich_description:
            return listing.model_copy(update={"description": self.enrich_description})
        return listing


def make_listing(token="a1", city="חיפה", price=5000, **overrides):
    base = dict(source="yad2", source_id=token, url=f"https://e.com/{token}", city=city, price=price)
    base.update(overrides)
    return Listing(**base)


def setup_alert(conn, filters=None):
    user = UserRepo(conn).upsert_google_user("g-1", "a@b.com", NOW)
    return AlertRepo(conn).create(user.id, "watch", filters or AlertFilters(locations=[Location(city="חיפה")]), ["telegram"], NOW)


def test_merge_preserving_enrichment():
    existing = make_listing(description="נוף לים", has_mamad=True, has_elevator=False)
    incoming = make_listing(price=4800)
    merged = merge_preserving_enrichment(existing, incoming)
    assert merged.price == 4800
    assert merged.description == "נוף לים"
    assert merged.has_mamad is True
    assert merged.has_elevator is False
    assert merge_preserving_enrichment(None, incoming) == incoming


async def test_new_listing_produces_event_and_notification(conn):
    alert = setup_alert(conn)
    source = FakeSource(listings=[make_listing()])
    notifier = LogNotifier()
    events = await run_cycle(conn, [source], notifier, NOW)
    assert len(events) == 1
    assert events[0].kind == "new"
    assert events[0].alert.id == alert.id
    assert notifier.sent == events
    assert SourceStateRepo(conn).get("yad2").last_success == NOW.isoformat()


async def test_second_cycle_same_data_no_events(conn):
    setup_alert(conn)
    source = FakeSource(listings=[make_listing()])
    await run_cycle(conn, [source], LogNotifier(), NOW)
    events = await run_cycle(conn, [source], LogNotifier(), LATER)
    assert events == []


async def test_price_drop_produces_event_price_rise_does_not(conn):
    setup_alert(conn)
    await run_cycle(conn, [FakeSource(listings=[make_listing(price=5000)])], LogNotifier(), NOW)
    drop_events = await run_cycle(conn, [FakeSource(listings=[make_listing(price=4500)])], LogNotifier(), LATER)
    assert [event.kind for event in drop_events] == ["price_drop"]
    assert drop_events[0].old_price == 5000
    rise_events = await run_cycle(
        conn, [FakeSource(listings=[make_listing(price=9000)])], LogNotifier(), LATER + timedelta(minutes=15)
    )
    assert rise_events == []


async def test_non_matching_listing_no_event(conn):
    setup_alert(conn, AlertFilters(locations=[Location(city="תל אביב")]))
    events = await run_cycle(conn, [FakeSource(listings=[make_listing(city="חיפה")])], LogNotifier(), NOW)
    assert events == []


async def test_no_active_locations_skips_sources(conn):
    source = FakeSource(listings=[make_listing()])
    events = await run_cycle(conn, [source], LogNotifier(), NOW)
    assert events == []
    assert source.fetch_calls == 0


async def test_disabled_source_skipped(conn):
    setup_alert(conn)
    SourceStateRepo(conn).set_enabled("yad2", False)
    source = FakeSource(listings=[make_listing()])
    events = await run_cycle(conn, [source], LogNotifier(), NOW)
    assert events == []
    assert source.fetch_calls == 0


async def test_failing_source_recorded_others_continue(conn):
    setup_alert(conn)
    bad = FakeSource(name="facebook", error=RuntimeError("session expired"))
    good = FakeSource(name="yad2", listings=[make_listing()])
    events = await run_cycle(conn, [bad, good], LogNotifier(), NOW)
    assert len(events) == 1
    state = SourceStateRepo(conn).get("facebook")
    assert state.last_error == "session expired"
    assert SourceStateRepo(conn).get("yad2").last_error is None


async def test_enrichment_only_for_new_and_persisted(conn):
    setup_alert(conn)
    source = FakeSource(listings=[make_listing()], enrich_description="חדש ומרוהט")
    await run_cycle(conn, [source], LogNotifier(), NOW)
    assert source.enriched_tokens == ["a1"]
    assert ListingRepo(conn).get("yad2:a1").description == "חדש ומרוהט"
    again = FakeSource(listings=[make_listing()])
    await run_cycle(conn, [again], LogNotifier(), LATER)
    assert again.enriched_tokens == []
    assert ListingRepo(conn).get("yad2:a1").description == "חדש ומרוהט"
