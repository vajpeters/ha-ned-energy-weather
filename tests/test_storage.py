"""Storage retention, same-day deduplication and restart."""

from datetime import UTC, datetime, timedelta

from custom_components.ned_energy_weather.models import Record
from custom_components.ned_energy_weather.storage import ForecastHistory


async def test_history_retention_and_restart(hass, record):
    first = ForecastHistory(hass, "test")
    now = datetime(2026, 10, 24, 22, tzinfo=UTC)
    first.days = {"2026-09-24": {}, "2026-09-26": {}}
    row = Record.parse(record(classification=1))
    await first.capture(now, {"0:2:1": (row,)})
    await first.capture(now + timedelta(minutes=30), {"0:2:1": (row,)})
    history = ForecastHistory(hass, "test")
    await history.load()
    assert set(history.days) == {"2026-09-26", "2026-10-25"}
    rows = history.series("0:2:1", now, now + timedelta(days=1))
    assert rows[0]["issued_at"] == now.isoformat()
    assert rows[0]["capacity"] == 438626
