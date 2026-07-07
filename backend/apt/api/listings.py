from typing import Literal

from fastapi import APIRouter, Query, Request

from apt.domain.models import AlertFilters, Location
from apt.repo.listings import ListingRepo
from apt.repo.scrape_set import ScrapeSetRepo

router = APIRouter()

MAX_LIMIT = 100


@router.get("/api/listings")
def search_listings(
    request: Request,
    city: str = Query(min_length=1),
    neighborhood: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_rooms: float | None = None,
    max_rooms: float | None = None,
    min_size_sqm: int | None = None,
    min_floor: int | None = None,
    max_floor: int | None = None,
    require_mamad: bool = False,
    require_elevator: bool = False,
    sort: Literal["newest", "price"] = "newest",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    state = request.app.state
    now = state.now_fn()
    location = Location(city=city.strip(), neighborhood=neighborhood or None)
    filters = AlertFilters(
        locations=[location],
        min_price=min_price, max_price=max_price,
        min_rooms=min_rooms, max_rooms=max_rooms,
        min_size_sqm=min_size_sqm,
        min_floor=min_floor, max_floor=max_floor,
        require_mamad=require_mamad, require_elevator=require_elevator,
    )
    scrape_set = ScrapeSetRepo(state.conn)
    known = {(loc.city, loc.neighborhood) for loc in scrape_set.active_locations(now)}
    newly_tracked = (location.city, location.neighborhood) not in known
    scrape_set.log_search(location, now)
    listings = ListingRepo(state.conn).search(
        filters, sort=sort, limit=max(1, min(limit, MAX_LIMIT)), offset=max(0, offset)
    )
    return {
        "listings": [listing.model_dump(mode="json") for listing in listings],
        "newly_tracked": newly_tracked,
    }
