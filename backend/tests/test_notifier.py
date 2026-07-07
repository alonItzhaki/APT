from datetime import datetime, timezone

from apt.domain.events import MatchEvent
from apt.domain.models import Alert, AlertFilters, Listing
from apt.notify.notifier import ChannelNotifier, price_key_for
from apt.repo.alerts import AlertRepo
from apt.repo.listings import ListingRepo
from apt.repo.notifications import NotificationRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


class FakeChannel:
    def __init__(self, name, applicable=True, fail=False):
        self.name = name
        self._applicable = applicable
        self._fail = fail
        self.delivered = []

    def applicable(self, user):
        return self._applicable

    async def deliver(self, user, event):
        if self._fail:
            raise RuntimeError("boom")
        self.delivered.append((user.id, event.listing.id))


def setup(conn, channels=("telegram",)):
    user = UserRepo(conn).upsert_google_user("g-1", "a@b.com", NOW)
    UserRepo(conn).set_telegram_chat(user.id, 42)
    alert = AlertRepo(conn).create(user.id, "x", AlertFilters(), list(channels), NOW)
    listing = Listing(source="yad2", source_id="a1", url="https://e.com/a1", city="חיפה", price=5000)
    ListingRepo(conn).upsert(listing, NOW)
    return user, alert, listing


def make_event(alert, listing, kind="new", old_price=None):
    return MatchEvent(kind=kind, listing=listing, alert=alert, old_price=old_price)


def make_bare_event(kind, price):
    listing = Listing(source="yad2", source_id="x", url="https://e.com/x", city="a", price=price)
    alert = Alert(id=1, user_id=1, name="n", filters=AlertFilters(), channels=["telegram"])
    return MatchEvent(kind=kind, listing=listing, alert=alert)


def test_price_key_for():
    assert price_key_for(make_bare_event("new", 5000)) == 0
    assert price_key_for(make_bare_event("price_drop", 4500)) == 4500
    assert price_key_for(make_bare_event("price_drop", None)) == 0


async def test_delivers_once_per_channel(conn):
    user, alert, listing = setup(conn, channels=("telegram", "email"))
    telegram, email = FakeChannel("telegram"), FakeChannel("email")
    notifier = ChannelNotifier(conn, {"telegram": telegram, "email": email}, now_fn=lambda: NOW)
    await notifier.send(make_event(alert, listing))
    await notifier.send(make_event(alert, listing))  # duplicate cycle
    assert telegram.delivered == [(user.id, listing.id)]
    assert email.delivered == [(user.id, listing.id)]


async def test_inapplicable_channel_skipped_without_claim(conn):
    user, alert, listing = setup(conn)
    channel = FakeChannel("telegram", applicable=False)
    notifier = ChannelNotifier(conn, {"telegram": channel}, now_fn=lambda: NOW)
    await notifier.send(make_event(alert, listing))
    assert channel.delivered == []
    assert NotificationRepo(conn).claim(alert.id, listing.id, "telegram", "new", 0, NOW) is True


async def test_delivery_failure_releases_claim_and_does_not_raise(conn):
    user, alert, listing = setup(conn)
    failing = FakeChannel("telegram", fail=True)
    notifier = ChannelNotifier(conn, {"telegram": failing}, now_fn=lambda: NOW)
    await notifier.send(make_event(alert, listing))  # must not raise
    working = FakeChannel("telegram")
    notifier2 = ChannelNotifier(conn, {"telegram": working}, now_fn=lambda: NOW)
    await notifier2.send(make_event(alert, listing))
    assert working.delivered == [(user.id, listing.id)]


async def test_unknown_channel_name_ignored(conn):
    user, alert, listing = setup(conn, channels=("telegram",))
    notifier = ChannelNotifier(conn, {}, now_fn=lambda: NOW)
    await notifier.send(make_event(alert, listing))  # must not raise


async def test_price_drop_renotifies_only_new_price(conn):
    user, alert, listing = setup(conn)
    channel = FakeChannel("telegram")
    notifier = ChannelNotifier(conn, {"telegram": channel}, now_fn=lambda: NOW)
    drop = make_event(alert, listing.model_copy(update={"price": 4500}), kind="price_drop", old_price=5000)
    await notifier.send(drop)
    await notifier.send(drop)
    deeper = make_event(alert, listing.model_copy(update={"price": 4000}), kind="price_drop", old_price=4500)
    await notifier.send(deeper)
    assert len(channel.delivered) == 2
