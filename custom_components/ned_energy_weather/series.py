"""Shared service and WebSocket query validation and serialization."""

from datetime import UTC, datetime, time, timedelta

import probatio
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError

from .api import AuthError, NedError
from .catalog import CATALOG
from .const import AMSTERDAM, CLASSIFICATIONS, DOMAIN, GRANULARITIES, PROVINCES, UNITS
from .models import timestamp
from .storage import history_key

SCHEMA = {
    probatio.Optional("area", default="netherlands"): probatio.Any(
        probatio.In(("netherlands", "province")),
        probatio.All(probatio.Coerce(int), probatio.Range(min=0, max=81)),
    ),
    probatio.Required("type_id"): probatio.All(probatio.Coerce(int), probatio.Range(min=0)),
    probatio.Required("activity"): probatio.All(probatio.Coerce(int), probatio.Range(min=1, max=7)),
    probatio.Optional("classification", default="actual"): probatio.In(
        (*CLASSIFICATIONS, "historical_forecast")
    ),
    probatio.Optional("granularity", default="hour"): probatio.In(GRANULARITIES),
    probatio.Required("start"): str,
    probatio.Required("end"): str,
}


def active(hass):
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry
    raise HomeAssistantError("Configure and load NED Energieweerbericht first")


def catalog_response(coordinator):
    return {
        "province": {"point_id": coordinator.province, "name": PROVINCES[coordinator.province]},
        "datasets": [
            {
                "point_id": point,
                "type_id": item.type_id,
                "activity": item.activity,
                "name": item.name,
                "category": item.category,
                "forecast_days": item.days,
                "fields": item.fields,
            }
            for point, item in coordinator.datasets
        ],
    }


async def get_series(entry, query):
    coordinator = entry.runtime_data
    area = query["area"]
    point = {"netherlands": 0, "province": coordinator.province}.get(area, area)
    type_id, activity = query["type_id"], query["activity"]
    item = CATALOG.get((type_id, activity))
    granularity = GRANULARITIES[query["granularity"]]
    if (
        item is None
        or point not in item.points
        or granularity not in item.granularities
        or (point in PROVINCES and point != coordinator.province)
    ):
        raise HomeAssistantError("Unsupported NED dataset, area or granularity")

    try:
        start, end = timestamp(query["start"]), timestamp(query["end"])
    except ValueError, OverflowError:
        raise HomeAssistantError("Use ISO 8601 timestamps with UTC offsets") from None
    now = datetime.now(UTC)
    if not now - timedelta(days=30, minutes=5) <= start < end <= now + timedelta(days=7):
        raise HomeAssistantError("Choose a range within the last 30 or next 7 days")
    classification = query["classification"]
    metadata = {
        "point_id": point,
        "type_id": type_id,
        "activity": activity,
        "name": item.name,
        "category": item.category,
        "classification": classification,
        "granularity": query["granularity"],
        "granularity_id": granularity,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "forecast_days": item.days,
        "aggregation_timezone": "Europe/Amsterdam" if granularity == 6 else "UTC",
    }
    response = {"metadata": metadata, "units": UNITS, "records": [], "availability": "empty"}
    if classification != "actual" and not item.days:
        return {**response, "availability": "unsupported"}
    if classification == "historical_forecast":
        if granularity != 5 or (point, item) not in coordinator.datasets:
            return {**response, "availability": "unsupported"}
        records = coordinator.history.series(
            history_key(point, type_id, activity), start, min(end, now)
        )
        return {**response, "records": records, "availability": "available" if records else "empty"}

    if classification == "forecast":
        start, end = max(start, now), min(end, now + timedelta(days=item.days))
    else:
        end = min(end, now)
    if end <= start:
        return response

    zone = AMSTERDAM if granularity == 6 else UTC
    cursor = start.astimezone(zone).date()
    stop = (end - timedelta(microseconds=1)).astimezone(zone).date() + timedelta(days=1)
    records = []
    stale = False
    while cursor < stop:
        block_end = min(stop, cursor + timedelta(days=5))
        historic = datetime.combine(block_end, time(), tzinfo=zone) <= now - timedelta(days=1)
        try:
            result = await coordinator.cache.get(
                points=(point,),
                types=(type_id,),
                activity=activity,
                classification=CLASSIFICATIONS[classification],
                granularity=granularity,
                start=cursor,
                end=block_end,
                ttl=21600 if historic else None,
            )
        except AuthError:
            entry.async_start_reauth()
            raise HomeAssistantError("NED rejected the credentials") from None
        except NedError as err:
            raise HomeAssistantError(str(err)) from None
        stale |= result.stale
        records.extend(row.as_response() for row in result.rows if start <= row.valid_from < end)
        cursor = block_end
    response["records"] = records
    response["availability"] = "stale" if stale else "available" if records else "empty"
    return response
