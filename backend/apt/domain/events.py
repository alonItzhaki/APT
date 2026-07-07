from typing import Literal

from pydantic import BaseModel

from apt.domain.models import Alert, Listing


class MatchEvent(BaseModel):
    kind: Literal["new", "price_drop"]
    listing: Listing
    alert: Alert
    old_price: int | None = None
