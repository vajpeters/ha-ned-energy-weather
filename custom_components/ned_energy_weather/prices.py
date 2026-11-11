"""Historical Dutch day-ahead prices from the public NED DRP export."""

import asyncio
import csv
from collections import OrderedDict
from datetime import UTC, date, datetime, time, timedelta
from math import isfinite
from time import monotonic

import aiohttp
import probatio
from homeassistant.exceptions import HomeAssistantError

from .const import AMSTERDAM

PRICE_URL = "https://nedapi.ned.nl/v1/pricesdownload"
FIRST_DAY = date(2023, 1, 1)
PRICE_SCHEMA = {probatio.Required("start"): str, probatio.Required("end"): str}


class PriceClient:
    """Fetch a bounded date range and share its cached response across callers."""

    def __init__(self, session):
        self.session = session
        self.cache = OrderedDict()
        self.lock = asyncio.Lock()

    async def get(self, query):
        try:
            start = date.fromisoformat(query["start"])
            end = date.fromisoformat(query["end"])
            if start.isoformat() != query["start"] or end.isoformat() != query["end"]:
                raise ValueError
        except ValueError:
            raise HomeAssistantError("Use dates in YYYY-MM-DD format") from None
        today = datetime.now(AMSTERDAM).date()
        if not FIRST_DAY <= start <= end <= today or (end - start).days >= 31:
            raise HomeAssistantError("Choose up to 31 days between 2023-01-01 and today")
        key = (start, end)
        async with self.lock:
            cached = self.cache.get(key)
            if cached and monotonic() < cached[0]:
                self.cache.move_to_end(key)
                return cached[1]
            result = await self._fetch(start, end)
            self.cache[key] = (monotonic() + (3600 if result["records"] else 300), result)
            self.cache.move_to_end(key)
            if len(self.cache) > 24:
                self.cache.popitem(last=False)
            return result

    async def _fetch(self, start, end):
        stop = end + timedelta(days=1)
        params = {
            "validfrom[after]": start.isoformat(),
            "validfrom[strictly_before]": stop.isoformat(),
            "granularity": "4",
            "responseType": "csv",
        }
        body = bytearray()
        try:
            async with self.session.get(
                PRICE_URL,
                params=params,
                headers={"Accept": "text/csv"},
                timeout=aiohttp.ClientTimeout(total=20),
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    raise HomeAssistantError(f"NED price download returned HTTP {response.status}")
                async for chunk in response.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > 512_000:
                        raise HomeAssistantError("NED price download exceeds the size limit")
        except aiohttp.ClientError, TimeoutError:
            raise HomeAssistantError("Could not reach the NED price download") from None

        lower = datetime.combine(start, time.min, AMSTERDAM).astimezone(UTC)
        upper = datetime.combine(stop, time.min, AMSTERDAM).astimezone(UTC)
        records = {}
        try:
            reader = csv.DictReader(body.decode("utf-8-sig").splitlines(), strict=True)
            if not {"validfrom", "validto", "electricity"} <= set(reader.fieldnames or ()):
                raise ValueError
            for row in reader:
                begin = datetime.fromisoformat(row["validfrom"])
                finish = datetime.fromisoformat(row["validto"])
                if begin.utcoffset() is None or finish.utcoffset() is None:
                    raise ValueError
                begin = begin.astimezone(UTC)
                finish = finish.astimezone(UTC)
                if finish - begin != timedelta(minutes=15):
                    raise ValueError
                value = (row["electricity"] or "").strip()
                if lower <= begin < finish <= upper and value not in ("", "N/A"):
                    price = float(value)
                    if not isfinite(price):
                        raise ValueError
                    records[begin] = {
                        "valid_from": begin.isoformat(),
                        "valid_to": finish.isoformat(),
                        "day_ahead": price,
                    }
        except csv.Error, ValueError, TypeError:
            raise HomeAssistantError("NED returned an invalid price CSV") from None

        return {
            "metadata": {
                "area": "netherlands",
                "granularity": "15min",
                "start": lower.isoformat(),
                "end": upper.isoformat(),
            },
            "units": {"day_ahead": "EUR/MWh"},
            "records": [records[begin] for begin in sorted(records)],
            "availability": "available" if records else "empty",
        }
