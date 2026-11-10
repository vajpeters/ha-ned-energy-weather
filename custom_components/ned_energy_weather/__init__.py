"""Set up the integration and its optional bundled card."""

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import NedClient
from .cache import Cache
from .const import DEFAULT_INTERVAL, DEFAULT_PROVINCE, DOMAIN, RESOURCE
from .coordinator import NedCoordinator
from .services import register_services
from .websocket import register_websocket

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass, config):
    register_services(hass)
    register_websocket(hass)
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                RESOURCE, str(Path(__file__).parent / "www" / Path(RESOURCE).name), False
            )
        ]
    )
    return True


async def async_setup_entry(hass, entry):
    province = entry.options.get("province", DEFAULT_PROVINCE)
    interval = entry.options.get("interval", DEFAULT_INTERVAL)
    cache = Cache(NedClient(async_get_clientsession(hass), entry.data["api_key"]), interval)
    coordinator = NedCoordinator(hass, entry, cache, province, interval)
    entry.runtime_data = coordinator
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.close()
    return True


async def async_remove_entry(hass, entry):
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.forecasts").async_remove()
