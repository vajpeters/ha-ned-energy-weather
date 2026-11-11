"""Authenticated access to configured metadata and time series."""

from homeassistant.components import websocket_api
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .prices import PRICE_SCHEMA
from .series import SCHEMA, active, catalog_response, get_series


@websocket_api.websocket_command({"type": f"{DOMAIN}/catalog"})
@websocket_api.async_response
async def websocket_catalog(hass, connection, msg):
    try:
        result = catalog_response(active(hass).runtime_data)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "ned_error", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({"type": f"{DOMAIN}/get_series", **SCHEMA})
@websocket_api.async_response
async def websocket_series(hass, connection, msg):
    try:
        result = await get_series(active(hass), msg)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "ned_error", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({"type": f"{DOMAIN}/get_prices", **PRICE_SCHEMA})
@websocket_api.async_response
async def websocket_prices(hass, connection, msg):
    try:
        result = await hass.data[DOMAIN].get(msg)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "ned_error", str(err))
        return
    connection.send_result(msg["id"], result)


def register_websocket(hass):
    websocket_api.async_register_command(hass, websocket_catalog)
    websocket_api.async_register_command(hass, websocket_series)
    websocket_api.async_register_command(hass, websocket_prices)
