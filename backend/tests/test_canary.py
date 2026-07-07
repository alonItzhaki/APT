from apt import canary
from apt.domain.models import Listing


class FakeSource:
    name = "yad2"

    def __init__(self, listings=None, error=None):
        self._listings = listings or []
        self._error = error

    async def fetch(self, locations):
        if self._error:
            raise self._error
        return self._listings

    async def enrich(self, listing):
        return listing


def make_listing():
    return Listing(source="yad2", source_id="a1", url="https://e.com/a1", city="חיפה")


async def test_canary_ok(capsys):
    assert await canary.run("חיפה", source=FakeSource([make_listing()])) == 0
    assert "1 listings" in capsys.readouterr().out


async def test_canary_empty_is_failure():
    assert await canary.run("חיפה", source=FakeSource([])) == 1


async def test_canary_error_is_2(capsys):
    assert await canary.run("חיפה", source=FakeSource(error=RuntimeError("403"))) == 2
    assert "403" in capsys.readouterr().out
