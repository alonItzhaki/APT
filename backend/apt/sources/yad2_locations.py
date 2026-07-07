from pydantic import BaseModel, ConfigDict

from apt.domain.models import Location


def normalize_text(value: str | None) -> str:
    value = (value or "").replace("קריית", "קרית")
    return "".join(value.split()).casefold()


class Yad2Query(BaseModel):
    model_config = ConfigDict(frozen=True)

    city_id: int
    area_id: int
    route_slug: str


# Seeded from the predecessor project (see yad2-reference-notes §7);
# supporting a new city = adding its Yad2 ids here.
KNOWN_CITIES: dict[str, Yad2Query] = {
    "תל אביב": Yad2Query(city_id=5000, area_id=1, route_slug="tel-aviv-area"),
    "חיפה": Yad2Query(city_id=4000, area_id=5, route_slug="coastal-north"),
    "קריית ים": Yad2Query(city_id=9600, area_id=6, route_slug="coastal-north"),
    "קריית מוצקין": Yad2Query(city_id=8200, area_id=6, route_slug="coastal-north"),
    "קריית ביאליק": Yad2Query(city_id=9500, area_id=6, route_slug="coastal-north"),
}

_BY_NORMALIZED = {normalize_text(name): query for name, query in KNOWN_CITIES.items()}


def resolve(location: Location) -> Yad2Query | None:
    return _BY_NORMALIZED.get(normalize_text(location.city))
