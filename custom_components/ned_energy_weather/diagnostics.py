"""Expose update health without including configuration or credentials."""

from datetime import UTC, datetime


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is None:
        return {"loaded": False}
    last = coordinator.last_success
    rows = tuple((coordinator.data or {}).values())
    latest = max((row.valid_to for row in rows), default=None)
    now = datetime.now(UTC)
    return {
        "api_available": coordinator.api_available,
        "last_success": last.isoformat() if last else None,
        "latest_interval_end": latest.isoformat() if latest else None,
        "data_age_seconds": max(0, (now - latest).total_seconds()) if latest else None,
        "stale_datasets": len(coordinator.stale),
        "province_point_id": coordinator.province,
        "snapshot_days": len(coordinator.history.days),
    }
