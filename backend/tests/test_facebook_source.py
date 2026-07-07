import pytest

from apt.domain.models import Listing, Location
from apt.sources.base import SourceError
from apt.sources.facebook import FacebookSource


async def test_fetch_without_session_raises_configuration_error():
    source = FacebookSource(session_file=None)
    with pytest.raises(SourceError, match="session file not configured"):
        await source.fetch([Location(city="חיפה")])


async def test_fetch_with_session_still_not_implemented(tmp_path):
    session = tmp_path / "fb-session.json"
    session.write_text("{}")
    source = FacebookSource(session_file=session)
    with pytest.raises(SourceError, match="not implemented"):
        await source.fetch([Location(city="חיפה")])


async def test_enrich_is_identity():
    listing = Listing(source="facebook", source_id="x", url="https://fb.com/x", city="חיפה")
    source = FacebookSource(session_file=None)
    assert await source.enrich(listing) == listing


def test_source_name():
    assert FacebookSource(session_file=None).name == "facebook"
