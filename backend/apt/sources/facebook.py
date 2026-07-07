"""Facebook source skeleton (post-v1 roadmap: real Marketplace scraping).

Kept Source-conformant and registered so the admin toggle, health reporting,
and cycle isolation all exercise the real code paths. Disabled by default;
enabling it without a provisioned session surfaces a clear error in admin
health instead of failing silently.
"""

from pathlib import Path

from apt.domain.models import Listing, Location
from apt.sources.base import SourceError


class FacebookSource:
    name = "facebook"

    def __init__(self, session_file: Path | None):
        self._session_file = session_file

    async def fetch(self, locations: list[Location]) -> list[Listing]:
        if self._session_file is None or not self._session_file.exists():
            raise SourceError("facebook: session file not configured (set APT_FB_SESSION_FILE)")
        raise SourceError("facebook: scraping not implemented yet - keep this source disabled")

    async def enrich(self, listing: Listing) -> Listing:
        return listing
