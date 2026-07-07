from typing import Protocol

from apt.domain.models import Listing, Location


class SourceError(Exception):
    """A source failed to fetch; the cycle records it and moves on."""


class Source(Protocol):
    name: str

    async def fetch(self, locations: list[Location]) -> list[Listing]: ...

    async def enrich(self, listing: Listing) -> Listing: ...
