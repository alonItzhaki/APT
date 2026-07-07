import logging
import sqlite3
from datetime import datetime, timezone
from typing import Callable, Protocol

from apt.domain.events import MatchEvent
from apt.domain.models import User
from apt.repo.notifications import NotificationRepo
from apt.repo.users import UserRepo

logger = logging.getLogger(__name__)


class Channel(Protocol):
    name: str

    def applicable(self, user: User) -> bool: ...

    async def deliver(self, user: User, event: MatchEvent) -> None: ...


def price_key_for(event: MatchEvent) -> int:
    if event.kind == "price_drop":
        return event.listing.price or 0
    return 0


class ChannelNotifier:
    """Claims exactly-once per (alert, listing, channel, kind, price) and delivers.

    send() never raises: the cycle has already recorded the listing, so an
    escaping exception would silently drop every remaining notification.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        channels: dict[str, Channel],
        now_fn: Callable[[], datetime] | None = None,
    ):
        self._conn = conn
        self._channels = channels
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    async def send(self, event: MatchEvent) -> None:
        try:
            await self._send(event)
        except Exception:
            logger.exception("notifier: unexpected failure for listing %s", event.listing.id)

    async def _send(self, event: MatchEvent) -> None:
        user = UserRepo(self._conn).get(event.alert.user_id)
        if user is None:
            logger.warning("notifier: user %s gone, skipping", event.alert.user_id)
            return
        notifications = NotificationRepo(self._conn)
        price_key = price_key_for(event)
        for channel_name in event.alert.channels:
            channel = self._channels.get(channel_name)
            if channel is None or not channel.applicable(user):
                continue
            if not notifications.claim(
                event.alert.id, event.listing.id, channel_name, event.kind, price_key, self._now_fn()
            ):
                continue
            try:
                await channel.deliver(user, event)
            except Exception as exc:
                logger.error(
                    "notifier: %s delivery failed for listing %s: %s",
                    channel_name, event.listing.id, exc,
                )
                notifications.release(
                    event.alert.id, event.listing.id, channel_name, event.kind, price_key
                )
