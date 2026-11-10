"""Periodic current readings and daily forecast capture."""

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthError, NedError
from .cache import Cache, Result
from .catalog import scope
from .const import AMSTERDAM, DOMAIN
from .models import Record
from .storage import ForecastHistory, history_key

_LOGGER = logging.getLogger(__name__)


def batches(items):
    """Group equal point sets so a collection filter cannot cross invalid pairs."""
    points = defaultdict(list)
    for point, item in items:
        points[item.activity, item.days, item.type_id].append(point)
    groups = defaultdict(list)
    for (activity, horizon, type_id), point_ids in points.items():
        groups[activity, horizon, tuple(sorted(point_ids))].append(type_id)
    for (activity, horizon, point_ids), types in groups.items():
        for offset in range(0, len(types), 5):
            yield activity, horizon, point_ids, tuple(sorted(types[offset : offset + 5]))


class NedCoordinator(DataUpdateCoordinator[dict[tuple[int, int, int], Record]]):
    def __init__(self, hass, entry, cache: Cache, province: int, interval: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval),
        )
        self.cache = cache
        self.province = province
        self.datasets = scope(province)
        self.history = ForecastHistory(hass, entry.entry_id)
        self.last_success: datetime | None = None
        self.api_available = False
        self.stale: set[tuple[int, int, int]] = set()
        self.snapshot_task: asyncio.Task | None = None
        self.force_next = False

    async def _async_setup(self) -> None:
        await self.history.load()

    async def _async_update_data(self):
        now = datetime.now(UTC)
        start = (now - timedelta(hours=12)).date()
        end = now.date() + timedelta(days=1)
        force, self.force_next = self.force_next, False
        groups = tuple(batches(self.datasets))
        responses = await asyncio.gather(
            *(
                self.cache.get(
                    points=points,
                    types=types,
                    activity=activity,
                    classification=2,
                    granularity=5,
                    start=start,
                    end=end,
                    force=force,
                )
                for activity, _, points, types in groups
            ),
            return_exceptions=True,
        )
        latest = dict(self.data or {})
        stale = set()
        successes = 0
        for (activity, _, points, types), result in zip(groups, responses, strict=True):
            keys = {(point, type_id, activity) for point in points for type_id in types}
            if isinstance(result, AuthError):
                self.api_available = False
                raise ConfigEntryAuthFailed(str(result)) from None
            if isinstance(result, NedError) or (isinstance(result, Result) and result.stale):
                stale.update(keys)
                continue
            if not isinstance(result, Result):
                raise result
            successes += 1
            for key in keys:
                latest.pop(key, None)
            for row in result.rows:
                if row.valid_from <= now:
                    key = (row.point_id, row.type_id, row.activity_id)
                    latest[key] = row
        self.stale = stale
        self.api_available = not stale
        if not successes:
            raise UpdateFailed("No fresh NED datasets available")
        self.last_success = now
        if self.snapshot_task is None or self.snapshot_task.done():
            self.snapshot_task = self.config_entry.async_create_background_task(
                self.hass, self._capture(), name="NED daily forecast snapshot"
            )
        return latest

    async def _capture(self) -> None:
        now = datetime.now(UTC)
        day = now.astimezone(AMSTERDAM).date()
        missing = [
            (point, item)
            for point, item in self.datasets
            if item.days
            and not self.history.collected(day, history_key(point, item.type_id, item.activity))
        ]
        if not missing:
            return
        collected = defaultdict(list)
        for activity, horizon, points, types in batches(missing):
            issued = datetime.now(UTC)
            try:
                result = await self.cache.get(
                    points=points,
                    types=types,
                    activity=activity,
                    classification=1,
                    granularity=5,
                    start=issued.date(),
                    end=(issued + timedelta(days=horizon)).date() + timedelta(days=1),
                )
            except AuthError, NedError:
                continue
            if result.stale:
                continue
            for row in result.rows:
                if now <= row.valid_from < now + timedelta(days=horizon):
                    collected[history_key(row.point_id, row.type_id, activity)].append(row)
        await self.history.capture(now, collected)

    async def force_refresh(self) -> None:
        self.force_next = True
        await self.async_refresh()

    async def close(self) -> None:
        if self.snapshot_task and not self.snapshot_task.done():
            self.snapshot_task.cancel()
            await asyncio.gather(self.snapshot_task, return_exceptions=True)
        await self.cache.close()
