from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apt.domain.events import MatchEvent
from apt.domain.models import Alert, AlertFilters, Listing, User
from apt.notify.email_channel import BREVO_URL, EmailChannel

USER = User(id=1, google_sub="g", email="user@example.com")


def make_event():
    listing = Listing(source="yad2", source_id="a1", url="https://e.com/a1", city="חיפה", price=5000)
    alert = Alert(id=1, user_id=1, name="x", filters=AlertFilters(), channels=["email"])
    return MatchEvent(kind="new", listing=listing, alert=alert)


def make_session(status=201, body="created"):
    response = MagicMock()
    response.status = status
    response.text = AsyncMock(return_value=body)
    request_ctx = MagicMock()
    request_ctx.__aenter__ = AsyncMock(return_value=response)
    request_ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post = MagicMock(return_value=request_ctx)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    return session_ctx, session


def test_applicable():
    channel = EmailChannel("key", "apt@example.com")
    assert channel.applicable(USER) is True
    assert channel.applicable(User(id=2, google_sub="h", email="")) is False


async def test_deliver_posts_to_brevo():
    session_ctx, session = make_session()
    with patch("apt.notify.email_channel.aiohttp.ClientSession", return_value=session_ctx):
        await EmailChannel("key-1", "apt@example.com").deliver(USER, make_event())
    args, kwargs = session.post.call_args
    assert args[0] == BREVO_URL
    payload = kwargs["json"]
    assert payload["to"] == [{"email": "user@example.com"}]
    assert payload["sender"]["email"] == "apt@example.com"
    assert "חיפה" in payload["subject"]
    assert 'dir="rtl"' in payload["htmlContent"]


async def test_deliver_raises_on_error_status():
    session_ctx, session = make_session(status=401, body="bad key")
    with patch("apt.notify.email_channel.aiohttp.ClientSession", return_value=session_ctx):
        with pytest.raises(RuntimeError, match="401"):
            await EmailChannel("key-1", "apt@example.com").deliver(USER, make_event())
