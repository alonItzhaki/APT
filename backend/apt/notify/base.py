import logging
from typing import Protocol

from apt.domain.events import MatchEvent


class Notifier(Protocol):
    async def send(self, event: MatchEvent) -> None: ...


class LogNotifier:
    """Records and logs match events until real channels land (plan 3)."""

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self.sent: list[MatchEvent] = []

    async def send(self, event: MatchEvent) -> None:
        self.sent.append(event)
        self._logger.info(
            "match %s: alert %s listing %s", event.kind, event.alert.id, event.listing.id
        )
