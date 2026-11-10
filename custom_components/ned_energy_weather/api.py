"""Bounded asynchronous client for NED utilization collections."""

import asyncio
import json
from collections import deque
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime

import aiohttp
from yarl import URL

from .const import API_URL
from .models import Record


class NedError(Exception):
    """An error safe to expose without request headers or response bodies."""


class AuthError(NedError):
    pass


class RateLimitError(NedError):
    pass


class NetworkError(NedError):
    pass


class TimeoutError(NedError):
    pass


class ResponseError(NedError):
    pass


class NedClient:
    """Share a bounded request budget across polling and user queries."""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self.session = session
        self._headers = {"X-AUTH-TOKEN": token, "Accept": "application/ld+json"}
        self._slots = asyncio.Semaphore(3)
        self._budget = asyncio.Lock()
        self._requests: deque[float] = deque()
        self._cooldown = 0.0

    async def _reserve(self) -> None:
        loop = asyncio.get_running_loop()
        async with self._budget:
            while True:
                now = loop.time()
                while self._requests and self._requests[0] <= now - 300:
                    self._requests.popleft()
                next_slot = self._requests[0] + 300 if len(self._requests) >= 200 else now
                wait = max(self._cooldown, next_slot) - now
                if wait <= 0:
                    self._requests.append(now)
                    return
                if wait > 15:
                    raise RateLimitError("NED request budget temporarily exhausted")
                await asyncio.sleep(wait)

    @staticmethod
    def _retry_delay(header: str | None, fallback: float) -> float:
        if header:
            try:
                return max(1, int(header))
            except ValueError:
                try:
                    return max(
                        1, (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds()
                    )
                except ValueError, TypeError, OverflowError:
                    pass
        return fallback

    async def _page(self, url: URL, params: list[tuple[str, str]] | None) -> dict:
        for attempt in range(3):
            delay = 2**attempt
            try:
                async with self._slots:
                    await self._reserve()
                    async with self.session.get(
                        url,
                        params=params,
                        headers=self._headers,
                        allow_redirects=False,
                        timeout=aiohttp.ClientTimeout(total=12),
                    ) as response:
                        if response.status in (401, 403):
                            raise AuthError("NED rejected the credentials")
                        if response.status == 429:
                            delay = self._retry_delay(response.headers.get("Retry-After"), delay)
                            loop = asyncio.get_running_loop()
                            self._cooldown = max(self._cooldown, loop.time() + delay)
                            error = RateLimitError("NED rate limit reached")
                        elif response.status >= 500:
                            error = NetworkError("NED is temporarily unavailable")
                        elif response.status != 200:
                            raise ResponseError(f"Unexpected NED HTTP status {response.status}")
                        else:
                            body = bytearray()
                            async for chunk in response.content.iter_chunked(65536):
                                body.extend(chunk)
                                if len(body) > 2_000_000:
                                    raise ResponseError("NED page exceeds the size limit")
                            try:
                                payload = json.loads(body)
                            except ValueError, UnicodeError, RecursionError:
                                raise ResponseError("Invalid NED JSON") from None
                            if not isinstance(payload, dict):
                                raise ResponseError("Invalid NED collection")
                            return payload
            except asyncio.TimeoutError:
                error = TimeoutError("NED request timed out")
            except aiohttp.ClientError:
                error = NetworkError("NED network request failed")
            if attempt == 2 or delay > 15:
                raise error from None
            await asyncio.sleep(delay)
        raise AssertionError("Retry loop exhausted")

    async def fetch(
        self,
        *,
        points: tuple[int, ...],
        types: tuple[int, ...],
        activity: int,
        classification: int,
        granularity: int,
        start: date,
        end: date,
    ) -> tuple[Record, ...]:
        """Read one date-aligned range, with exclusive end."""
        params = [
            ("itemsPerPage", "200"),
            ("activity", str(activity)),
            ("classification", str(classification)),
            ("granularity", str(granularity)),
            ("granularitytimezone", "1" if granularity == 6 else "0"),
            ("validfrom[after]", start.isoformat()),
            ("validfrom[strictly_before]", end.isoformat()),
        ]
        for key, ids in (("point", points), ("type", types)):
            params.extend((key if len(ids) == 1 else f"{key}[]", str(item)) for item in ids)
        base = URL(API_URL)
        url = base
        seen: set[URL] = set()
        records: dict[tuple[int, int, datetime], Record] = {}
        for _ in range(80):
            if url in seen:
                raise ResponseError("Repeated NED pagination link")
            seen.add(url)
            payload = await self._page(url, params)
            members = payload.get("hydra:member", payload.get("member"))
            view = payload.get("hydra:view", payload.get("view", {}))
            if not isinstance(members, list) or not isinstance(view, dict):
                raise ResponseError("Invalid NED collection structure")
            for member in members:
                try:
                    record = Record.parse(member)
                except KeyError, ValueError, TypeError, AttributeError, OverflowError:
                    raise ResponseError("Invalid NED utilization record") from None
                if (
                    record.point_id not in points
                    or record.type_id not in types
                    or record.activity_id != activity
                    or record.classification != classification
                    or record.granularity != granularity
                ):
                    raise ResponseError("NED returned records outside the requested filters")
                records[record.point_id, record.type_id, record.valid_from] = record
            if len(records) > 10_000:
                raise ResponseError("NED query exceeds the record limit")
            next_page = view.get("hydra:next", view.get("next"))
            if not next_page:
                return tuple(sorted(records.values(), key=lambda row: row.valid_from))
            try:
                url = url.join(URL(next_page))
                safe = url.origin() == base.origin() and url.path == base.path
                safe = safe and url.user is None and url.password is None
            except ValueError, TypeError:
                safe = False
            if not safe:
                raise ResponseError("Invalid NED pagination link")
            params = None
        raise ResponseError("NED query exceeds the page limit")
