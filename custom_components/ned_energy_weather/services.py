"""Register Home Assistant actions once, independent of the entry lifecycle."""

import probatio
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.service import async_register_admin_service

from .const import DOMAIN
from .prices import PRICE_SCHEMA
from .series import SCHEMA, active, get_series


def register_services(hass):
    async def prices(call):
        return await hass.data[DOMAIN].get(call.data)

    async def series(call):
        return await get_series(active(hass), call.data)

    async def refresh(call):
        coordinator = active(hass).runtime_data
        await coordinator.force_refresh()
        if not coordinator.api_available:
            raise HomeAssistantError("NED refresh could not update all datasets")

    hass.services.async_register(
        DOMAIN,
        "get_series",
        series,
        schema=probatio.Schema(SCHEMA),
        supports_response=SupportsResponse.ONLY,
    )
    async_register_admin_service(hass, DOMAIN, "refresh", refresh, schema=probatio.Schema({}))
    hass.services.async_register(
        DOMAIN,
        "get_prices",
        prices,
        schema=probatio.Schema(PRICE_SCHEMA),
        supports_response=SupportsResponse.ONLY,
    )
