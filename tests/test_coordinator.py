"""Shared in-flight cache and stale-data behavior."""

import asyncio
from unittest.mock import AsyncMock

from custom_components.ned_energy_weather.api import NetworkError
from custom_components.ned_energy_weather.cache import Cache


async def test_cache_shares_request_and_preserves_last_result():
    client = AsyncMock()
    client.fetch.return_value = ("sample",)
    cache = Cache(client, 60)
    first, second = await asyncio.gather(cache.get(points=(0,)), cache.get(points=(0,)))
    assert first is second
    client.fetch.assert_awaited_once()
    client.fetch.side_effect = NetworkError("Unavailable")
    assert (await cache.get(points=(0,), force=True)).stale
    assert (await cache.get(points=(0,))).rows == ("sample",)
    await cache.close()
