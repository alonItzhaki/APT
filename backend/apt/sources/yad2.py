import asyncio
import json
import logging
import random

import aiohttp
from bs4 import BeautifulSoup

from apt.domain.models import Listing, Location
from apt.sources import yad2_parse
from apt.sources.base import SourceError
from apt.sources.yad2_locations import Yad2Query, normalize_text, resolve

logger = logging.getLogger(__name__)

RENT_PAGE_URL = "https://www.yad2.co.il/realestate/rent/{route_slug}?area={area}&city={city}"
RENT_DATA_URL = "https://www.yad2.co.il/realestate/_next/data/{build_id}/rent/{route_slug}.json"
ITEM_DATA_URL = "https://www.yad2.co.il/realestate/_next/data/{build_id}/item/{route_slug}/{token}.json"

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
DEFAULT_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Priority': 'u=0, i',
    'Sec-Ch-Ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': USER_AGENT,
}

REQUEST_TIMEOUT_SECONDS = 30
MAX_PAGES_PER_QUERY = 10
RETRY_STATUSES = {500, 502, 503, 504}


def _matches_any(listing: Listing, locations: list[Location]) -> bool:
    for location in locations:
        if normalize_text(listing.city) != normalize_text(location.city):
            continue
        if location.neighborhood is None:
            return True
        if normalize_text(listing.neighborhood) == normalize_text(location.neighborhood):
            return True
    return False


class Yad2Source:
    name = "yad2"

    def __init__(self, min_delay: float = 2.0, max_delay: float = 8.0):
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._build_id: str | None = None
        self._route_slug_by_token: dict[str, str] = {}

    @staticmethod
    def _timeout() -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

    async def _sleep_politely(self) -> None:
        await asyncio.sleep(random.uniform(self._min_delay, self._max_delay))

    async def _fetch_build_id(self, session: aiohttp.ClientSession, query: Yad2Query) -> str:
        if self._build_id is not None:
            return self._build_id
        url = RENT_PAGE_URL.format(
            route_slug=query.route_slug, area=query.area_id, city=query.city_id
        )
        async with session.get(url) as response:
            response.raise_for_status()
            html = await response.text()
        script = BeautifulSoup(html, "html.parser").find("script", id="__NEXT_DATA__")
        if script is None or not script.string:
            raise SourceError("yad2: __NEXT_DATA__ script not found")
        self._build_id = json.loads(script.string)["buildId"]
        return self._build_id

    async def _get_json(self, session: aiohttp.ClientSession, url: str, params=None) -> dict:
        for attempt in range(3):
            async with session.get(url, params=params) as response:
                if response.status in RETRY_STATUSES:
                    await asyncio.sleep(2**attempt)
                    continue
                response.raise_for_status()
                return await response.json()
        raise SourceError(f"yad2: server errors persisted for {url}")

    async def fetch(self, locations: list[Location]) -> list[Listing]:
        grouped: dict[Yad2Query, list[Location]] = {}
        for location in locations:
            query = resolve(location)
            if query is None:
                logger.warning("yad2: no city mapping for %r - skipped", location.city)
                continue
            grouped.setdefault(query, []).append(location)

        results: list[Listing] = []
        seen: set[str] = set()
        async with aiohttp.ClientSession(headers=DEFAULT_HEADERS, timeout=self._timeout()) as session:
            first_request = True
            for query, query_locations in grouped.items():
                build_id = await self._fetch_build_id(session, query)
                url = RENT_DATA_URL.format(build_id=build_id, route_slug=query.route_slug)
                page, pages_total = 1, 1
                while page <= pages_total:
                    if not first_request:
                        await self._sleep_politely()
                    first_request = False
                    data = await self._get_json(
                        session, url,
                        params={"area": query.area_id, "city": query.city_id, "page": page},
                    )
                    feed = yad2_parse.extract_feed(data)
                    reported_pages = yad2_parse.total_pages(feed)
                    if reported_pages > MAX_PAGES_PER_QUERY:
                        logger.warning(
                            "yad2: %s reports %d pages, scraping first %d only",
                            query.route_slug, reported_pages, MAX_PAGES_PER_QUERY,
                        )
                    pages_total = min(reported_pages, MAX_PAGES_PER_QUERY)
                    for listing in yad2_parse.parse_feed_items(feed):
                        if listing.source_id in seen or not _matches_any(listing, query_locations):
                            continue
                        seen.add(listing.source_id)
                        self._route_slug_by_token[listing.source_id] = query.route_slug
                        results.append(listing)
                    page += 1
        return results

    async def enrich(self, listing: Listing) -> Listing:
        route_slug = self._route_slug_by_token.get(listing.source_id)
        if route_slug is None or self._build_id is None:
            return listing
        url = ITEM_DATA_URL.format(
            build_id=self._build_id, route_slug=route_slug, token=listing.source_id
        )
        try:
            async with aiohttp.ClientSession(headers=DEFAULT_HEADERS, timeout=self._timeout()) as session:
                data = await self._get_json(session, url)
        except Exception as exc:
            logger.warning("yad2: detail fetch failed for %s: %s", listing.source_id, exc)
            return listing
        return yad2_parse.apply_item_detail(listing, yad2_parse.extract_item_detail(data))
