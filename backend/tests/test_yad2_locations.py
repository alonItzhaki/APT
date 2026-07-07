from apt.domain.models import Location
from apt.sources.yad2_locations import KNOWN_CITIES, Yad2Query, normalize_text, resolve


def test_normalize_text_whitespace_case_and_kiryat():
    assert normalize_text("  תל  אביב ") == "תלאביב"
    assert normalize_text("קריית ים") == normalize_text("קרית ים")
    assert normalize_text(None) == ""


def test_resolve_known_city():
    query = resolve(Location(city="חיפה"))
    assert query == Yad2Query(city_id=4000, area_id=5, route_slug="coastal-north")


def test_resolve_tolerates_spelling_variant():
    assert resolve(Location(city="קרית ים")) == KNOWN_CITIES["קריית ים"]


def test_resolve_unknown_city_returns_none():
    assert resolve(Location(city="עיר לא קיימת")) is None


def test_yad2_query_is_hashable():
    assert len({resolve(Location(city="חיפה")), resolve(Location(city="חיפה"))}) == 1
