"""Bounded TTL cache with shared in-flight requests and stale fallback."""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic

from .api import AuthError, NedClient, NetworkError, RateLimitError, TimeoutError
from .models import Record


@dataclass(frozen=True)
class Result:
    rows: tuple[Record, ...]
    stale: bool = False


class Cache:
    def __init__(self, client: NedClient, interval: int) -> None:
        self.client = client
        self.interval = interval
        self.values: OrderedDict[tuple, tuple[float, Result]] = OrderedDict()
        self.pending: dict[tuple, asyncio.Task[Result]] = {}

    async def get(self, *, ttl: int | None = None, force: bool = False, **query) -> Result:
        key = tuple(sorted(query.items()))
        saved = self.values.get(key)
        if saved and not force and saved[0] > monotonic():
            self.values.move_to_end(key)
            return saved[1]
        if key not in self.pending:
            if len(self.pending) >= 24:
                raise RateLimitError("Too many concurrent NED queries")
            self.pending[key] = asyncio.create_task(
                self._fetch(key, ttl if ttl is not None else self.interval * 60, query)
            )
            self.pending[key].add_done_callback(self._observe)
        return await asyncio.shield(self.pending[key])

    @staticmethod
    def _observe(task: asyncio.Task) -> None:
        if not task.cancelled():
            task.exception()

    async def _fetch(self, key: tuple, ttl: int, query: dict) -> Result:
        try:
            result = Result(await self.client.fetch(**query))
            self.values[key] = (monotonic() + ttl, result)
            self.values.move_to_end(key)
            while len(self.values) > 48:
                self.values.popitem(last=False)
            return result
        except AuthError:
            raise
        except NetworkError, RateLimitError, TimeoutError:
            if key not in self.values:
                raise
            return Result(self.values[key][1].rows, stale=True)
        finally:
            self.pending.pop(key, None)

    async def close(self) -> None:
        tasks = tuple(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
