from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from telegram.error import Forbidden, RetryAfter

from apt.domain.events import MatchEvent
from apt.domain.models import AlertFilters, Listing, User
from apt.notify.telegram_channel import TelegramChannel
from apt.repo.alerts import AlertRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


def make_event(conn):
    user = UserRepo(conn).upsert_google_user("g-1", "a@b.com", NOW)
    UserRepo(conn).set_telegram_chat(user.id, 42)
    alert = AlertRepo(conn).create(user.id, "x", AlertFilters(), ["telegram"], NOW)
    listing = Listing(source="yad2", source_id="a1", url="https://e.com/a1", city="חיפה", price=5000)
    return UserRepo(conn).get(user.id), MatchEvent(kind="new", listing=listing, alert=alert)


def test_applicable(conn):
    channel = TelegramChannel(conn, AsyncMock())
    assert channel.applicable(User(id=1, google_sub="g", email="e", telegram_chat_id=5)) is True
    assert channel.applicable(User(id=1, google_sub="g", email="e")) is False


async def test_deliver_sends_html(conn):
    bot = AsyncMock()
    user, event = make_event(conn)
    await TelegramChannel(conn, bot).deliver(user, event)
    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == 42
    assert kwargs["parse_mode"] == "HTML"
    assert "₪5,000" in kwargs["text"]


async def test_retry_after_then_success(conn, monkeypatch):
    import apt.notify.telegram_channel as mod
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    bot = AsyncMock()
    bot.send_message.side_effect = [RetryAfter(3), None]
    user, event = make_event(conn)
    await TelegramChannel(conn, bot).deliver(user, event)
    assert bot.send_message.call_count == 2
    assert sleeps == [4]


async def test_forbidden_unlinks_user_without_raising(conn):
    bot = AsyncMock()
    bot.send_message.side_effect = Forbidden("blocked")
    user, event = make_event(conn)
    await TelegramChannel(conn, bot).deliver(user, event)
    assert UserRepo(conn).get(user.id).telegram_chat_id is None


async def test_other_errors_propagate(conn):
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("network down")
    user, event = make_event(conn)
    with pytest.raises(RuntimeError):
        await TelegramChannel(conn, bot).deliver(user, event)
