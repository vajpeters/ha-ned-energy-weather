"""Daily hour-resolution forecast snapshots in Home Assistant storage."""

import json
from datetime import UTC, date, datetime, timedelta

from homeassistant.helpers.storage import Store

from .const import AMSTERDAM, DOMAIN, UNITS
from .models import Record

MAX_BYTES = 8_000_000


class ForecastHistory:
    def __init__(self, hass, entry_id: str) -> None:
        self.store = Store(hass, 1, f"{DOMAIN}.{entry_id}.forecasts")
        self.days: dict = {}

    async def load(self) -> None:
        self.days = await self.store.async_load() or {}

    def prune(self, today: date) -> None:
        earliest = (today - timedelta(days=29)).isoformat()
        self.days = {day: value for day, value in self.days.items() if day >= earliest}

    async def capture(self, now: datetime, groups: dict[str, tuple[Record, ...]]) -> None:
        day = now.astimezone(AMSTERDAM).date().isoformat()
        self.prune(date.fromisoformat(day))
        snapshot = self.days.setdefault(day, {})
        for key, rows in groups.items():
            if key not in snapshot and rows:
                snapshot[key] = [
                    int(now.timestamp()),
                    [
                        [
                            int(row.valid_from.timestamp()),
                            int(row.valid_to.timestamp()),
                            int(row.last_update.timestamp()) if row.last_update else None,
                            *row.values,
                        ]
                        for row in rows
                    ],
                ]
        if not snapshot:
            self.days.pop(day, None)
        while self.days and len(json.dumps(self.days, separators=(",", ":"))) > MAX_BYTES:
            del self.days[min(self.days)]
        await self.store.async_save(self.days)

    def collected(self, today: date, key: str) -> bool:
        return key in self.days.get(today.isoformat(), {})

    def series(self, key: str, start: datetime, end: datetime) -> list[dict]:
        """Pick the newest saved forecast preceding each target interval."""

        def iso(value: int) -> str:
            return datetime.fromtimestamp(value, UTC).isoformat()

        rows = {}
        for _, snapshot in sorted(self.days.items()):
            if key not in snapshot:
                continue
            issued, samples = snapshot[key]
            for begin, finish, updated, *values in samples:
                if start.timestamp() <= begin < end.timestamp() and issued <= begin:
                    rows[begin] = {
                        "valid_from": iso(begin),
                        "valid_to": iso(finish),
                        "last_update": iso(updated) if updated is not None else None,
                        "issued_at": iso(issued),
                        **dict(zip(UNITS, values, strict=True)),
                    }
        return [rows[begin] for begin in sorted(rows)]


def history_key(point: int, type_id: int, activity: int) -> str:
    return f"{point}:{type_id}:{activity}"
