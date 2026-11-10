"""Exercise the integration through the actual Home Assistant entry points."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant.common import MockConfigEntry
from yaml import safe_load

from custom_components.ned_energy_weather.api import AuthError, NedClient
from custom_components.ned_energy_weather.const import DOMAIN, RESOURCE
from custom_components.ned_energy_weather.models import Record


@pytest.fixture
def ned_api(monkeypatch, record):
    async def fetch(**query):
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        begin = (
            now - timedelta(hours=1) if query["classification"] == 2 else now + timedelta(hours=1)
        )
        return tuple(
            Record.parse(
                record(
                    point=point,
                    type_id=type_id,
                    activity=query["activity"],
                    classification=query["classification"],
                    granularity=query["granularity"],
                    start=begin.isoformat(),
                    end=(begin + timedelta(hours=1)).isoformat(),
                )
            )
            for point in query["points"]
            for type_id in query["types"]
            if query["start"] <= begin.date() < query["end"]
        )

    mock = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(NedClient, "fetch", mock)
    return mock


@pytest.fixture
async def loaded(hass, enable_custom_integrations, ned_api):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"api_key": "test-token"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield entry
    assert await hass.config_entries.async_unload(entry.entry_id)


def query(classification="actual"):
    now = datetime.now(UTC)
    return {
        "type_id": 2,
        "activity": 1,
        "classification": classification,
        "start": (now - timedelta(days=1)).isoformat(),
        "end": (now + timedelta(days=1)).isoformat(),
    }


async def test_flow_and_options(hass, enable_custom_integrations, ned_api):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    inputs = {"api_key": "first-key", "province": 7, "interval": 60}
    response = await hass.config_entries.flow.async_configure(result["flow_id"], inputs)
    assert response["type"] is FlowResultType.CREATE_ENTRY
    entry = response["result"]
    await hass.async_block_till_done()
    options = await hass.config_entries.options.async_init(entry.entry_id)
    response = await hass.config_entries.options.async_configure(
        options["flow_id"],
        {"province": 8, "interval": 15},
    )
    assert response["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.province == 8
    reconfigure = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    response = await hass.config_entries.flow.async_configure(
        reconfigure["flow_id"],
        {"api_key": "replacement-key"},
    )
    assert response["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data["api_key"] == "replacement-key"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_config_flow_rejects_bad_key(hass, enable_custom_integrations, ned_api):
    ned_api.side_effect = AuthError("NED rejected the credentials")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    response = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"api_key": "invalid", "province": 7, "interval": 60},
    )
    assert response["errors"] == {"base": "invalid_auth"}


async def test_actions_and_sensors(hass, loaded):
    assert hass.states.get("sensor.ned_solar_nederland_capacity").state == "438626.0"
    for classification in ("actual", "forecast"):
        result = await hass.services.async_call(
            DOMAIN,
            "get_series",
            query(classification),
            blocking=True,
            return_response=True,
        )
        assert result["availability"] == "available"
        assert result["records"][0]["capacity"] == 438626
        assert "test-token" not in json.dumps(result)
    with pytest.raises(HomeAssistantError, match="Unsupported"):
        await hass.services.async_call(
            DOMAIN,
            "get_series",
            {**query(), "type_id": 17, "area": "province"},
            blocking=True,
            return_response=True,
        )
    await hass.services.async_call(DOMAIN, "refresh", blocking=True)


async def test_websocket_and_resource(hass, loaded, hass_ws_client, hass_client):
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": f"{DOMAIN}/get_series", **query()})
    result = await ws.receive_json()
    assert result["success"]
    assert result["result"]["units"]["capacity"] == "kW"
    await ws.send_json({"id": 2, "type": f"{DOMAIN}/catalog"})
    result = await ws.receive_json()
    assert result["result"]["province"]["point_id"] == 7
    http = await hass_client(hass)
    response = await http.get(RESOURCE)
    assert response.status == 200
    assert "customElements.define" in await response.text()


def test_repository_metadata():
    root = Path(__file__).resolve().parents[1]
    component = root / "custom_components" / DOMAIN
    manifest = json.loads((component / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == DOMAIN and manifest["config_flow"]
    assert manifest["version"] == "0.1.0"
    assert (
        json.loads((root / "hacs.json").read_text(encoding="utf-8"))["homeassistant"] == "2026.11.0"
    )
    for lang in ("nl", "en"):
        translations = json.loads(
            (component / f"translations/{lang}.json").read_text(encoding="utf-8")
        )
        assert set(translations["config"]["step"]) == {"user", "reauth_confirm", "reconfigure"}
    assert set(safe_load((component / "services.yaml").read_text(encoding="utf-8"))) == {
        "get_series",
        "refresh",
    }
