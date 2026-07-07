import pytest
from pydantic import ValidationError

from apt.domain.events import MatchEvent
from apt.domain.models import Alert, AlertFilters, Listing
from apt.notify.base import LogNotifier


def make_listing():
    return Listing(source="yad2", source_id="x1", url="https://e.com/x1", city="חיפה")


def make_alert():
    return Alert(id=1, user_id=1, name="a", filters=AlertFilters(), channels=["telegram"])


def test_match_event_kinds():
    event = MatchEvent(kind="new", listing=make_listing(), alert=make_alert())
    assert event.old_price is None
    drop = MatchEvent(kind="price_drop", listing=make_listing(), alert=make_alert(), old_price=6000)
    assert drop.old_price == 6000
    with pytest.raises(ValidationError):
        MatchEvent(kind="price_rise", listing=make_listing(), alert=make_alert())


async def test_log_notifier_records_events():
    notifier = LogNotifier()
    event = MatchEvent(kind="new", listing=make_listing(), alert=make_alert())
    await notifier.send(event)
    assert notifier.sent == [event]
