"""Live Yad2 canary: one real fetch, nonzero exit when the contract drifted."""

import asyncio
import sys

from apt.domain.models import Location
from apt.sources.base import Source
from apt.sources.yad2 import Yad2Source


async def run(city: str, source: Source | None = None) -> int:
    source = source or Yad2Source(min_delay=0.5, max_delay=1.5)
    try:
        listings = await source.fetch([Location(city=city)])
    except Exception as exc:
        print(f"yad2 canary FAILED: {exc}")
        return 2
    print(f"yad2 canary: {len(listings)} listings for {city}")
    return 0 if listings else 1


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else "חיפה")))


if __name__ == "__main__":
    main()
