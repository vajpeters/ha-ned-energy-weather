# NED Energieweerbericht 0.1.0

[Nederlandse documentatie](README.md)

A standalone integration for Dutch national and provincial energy data from the Nationaal Energie Dashboard (NED). Requires Home Assistant **2026.11.0 or newer** and a NED API key. National solar forecasts describe nationwide generation and cannot predict the output of your own panels.

## Install and configure

1. Create a NED account, open **My account → API**, and generate a key.
2. Install using one of these methods:
   - **Manual** — copy the complete `custom_components/ned_energy_weather` directory to `/config/custom_components/`, then restart Home Assistant.
   - **Marketplace** — after publication, open **Settings → Marketplace → Add from link**. Connect GitHub if prompted, provide the public repository URL, and install as an integration. Restart when prompted.
   - **HACS** — open **HACS → menu → Custom repositories**, add the URL as an **Integration**, download it, and restart.
3. Open **Settings → Devices & services → Add integration** and search for **NED Energieweerbericht**. Enter the key and choose one province and a 15, 30, 60, 120 or 360 minute interval. Defaults are Utrecht and 60 minutes. National data is always available.
4. Use **Configure** to change the province or interval. Use **Reconfigure** in the integration menu to replace the API key. An expired or revoked key triggers reauthentication.

## Datasets and sensors

The catalog contains 39 type/activity combinations. It covers electricity generation (solar, onshore/offshore wind, gas, coal, nuclear, biomass, waste, combined heat and power, other and total), electricity consumption, heat and renewable energy (biogas, biomethane, heat pumps, geothermal, solar thermal and other), gas consumption, cross-border electricity, gas flows and gas storage.

Sensors and the card cover the Netherlands and the selected province. Only solar (type 2) and onshore wind (type 1) have provincial datasets in the catalog. Gas import, export, injection and withdrawal are available via the series action with their individual NED Point IDs. National gas storage is type 28, activity 7. Activities 1–7 mean providing, consuming, import, export, storage injection, storage withdrawal and storage. The catalog documents all IDs and per-activity horizons.

Each in-scope dataset has a device with hourly readings. Capacity (average power, kW) is enabled by default. Enable interval volume (kWh), utilization (%), CO₂ emissions (kg), and emission factor (kg/kWh) in the entity registry as needed. Emission fields are exposed for datasets marked as having CO₂ data. NED can omit individual measurements. Volume is an interval amount and has no accumulating state class. Use Home Assistant history graphs for recorded sensor states. Recorder builds this history after installation.

## Time series actions

`ned_energy_weather.get_series` requires response data. Provide `type_id`, `activity`, and offset-aware ISO 8601 timestamps for `start` (inclusive) and `end` (exclusive). `area` accepts `netherlands`, `province` or an allowed numeric Point ID. Use `15min`, `hour` or `day` for `granularity`. Set `classification` to `actual`, `forecast`, or `historical_forecast` (saved hourly snapshots). The response contains `metadata`, `units`, `records`, and `availability` (`available`, `empty`, `unsupported`, `stale`). Record timestamps are UTC and missing measurements are `null`. Saved forecasts also provide `issued_at`. Administrators can call `ned_energy_weather.refresh` to update current hourly readings immediately.

The following examples use the response in the automation trace. They are documentation examples and do not ship as configured automations.

```yaml
alias: NED - Read provincial solar history
triggers:
  - trigger: time
    at: "08:10:00"
actions:
  - action: ned_energy_weather.get_series
    data:
      area: province
      type_id: 2
      activity: 1
      classification: actual
      granularity: hour
      start: "{{ (utcnow() - timedelta(hours=24)).isoformat() }}"
      end: "{{ utcnow().isoformat() }}"
    response_variable: ned_solar
  - variables:
      sample_count: "{{ ned_solar.records | count }}"
mode: single
```

```yaml
alias: NED - Read national wind forecast
triggers:
  - trigger: time
    at: "13:10:00"
actions:
  - action: ned_energy_weather.get_series
    data:
      area: netherlands
      type_id: 1
      activity: 1
      classification: forecast
      granularity: 15min
      start: "{{ utcnow().isoformat() }}"
      end: "{{ (utcnow() + timedelta(hours=24)).isoformat() }}"
    response_variable: ned_wind
  - variables:
      sample_count: "{{ ned_wind.records | count }}"
mode: single
```

## Lovelace card

Enable Advanced Mode in your profile if Resources is hidden. Open **Settings → Dashboards → Resources**, then add `/api/ned_energy_weather/ned-energy-weather-card.js` as a **JavaScript module**. Add a manual card:

```yaml
type: custom:ned-energy-weather-card
title: NED Energieweerbericht
area: netherlands
granularity: hour
datasets: ["2:1", "1:1", "51:1"]
```

Choose an area, up to four datasets, a measurement, a resolution and past/future display windows. Select **Ophalen** (Load). The chart shows actual readings, future forecasts and any saved earlier hourly forecasts. Timestamps use the Home Assistant time zone. Only the integration backend contacts NED.

## API, time zones and retention

- NED allows 200 requests per five minutes. Pagination and retries count toward the local limit. The client uses at most three concurrent requests and honors `Retry-After`. Other software using the same NED account can also consume quota.
- Sensors fetch recent hourly data. The series action fetches at most 30 days of history in bounded date blocks. During a temporary failure, series data may come from an expired cache and is marked `stale`. Affected sensors become unavailable while their latest readings are retained internally.
- Forecast horizons are one or seven days where offered. For each configured series the first successful hourly forecast is saved per Amsterdam calendar day. Comparisons pick the most recent locally saved forecast from before each target interval. There is no pre-installation backfill or long-term reference series. Storage retains up to 30 calendar days and approximately 8 MB, removing the oldest days first.
- The endpoint is `https://api.ned.nl/v1/utilizations`. The older `api.netanders.io` hostname has been retired. The parameter table defines UTC as timezone ID 0 and Amsterdam as 1, correcting the label in the old example. Daily aggregates require ID 1 and can span 23 or 25 hours. The client converts the utilization ratio from JSON-LD into a percentage.
- OpenAPI confirms the `point[]` and `type[]` collection filters, Hydra pagination and a maximum of 200 records per page. Some field descriptions lag the catalog, including support for 15-minute data and newer activities. OpenAPI describes `emission` using tonnes, while the manual and API overview specify kg. The integration follows the manual. The emissions unit and percentage conversion still need confirmation against an authenticated production response. Tests use simulated JSON-LD responses.

## Troubleshoot, update and remove

- **Invalid key** — generate a fresh NED key and use **Reconfigure**.
- **429 or slow requests** — retry later with a shorter time window and check whether other applications use the same key.
- **Empty series** — check the area, activity, resolution and classification. NED data can arrive late. A historical forecast comparison requires a saved forecast.
- **Missing card** — check the URL and JavaScript module type, reload the browser and confirm the integration is loaded.
- **Diagnostics** — the diagnostic sensor exposes the last successful refresh and API availability. Download diagnostics from the integration menu for data freshness and storage status. The diagnostics omit credentials. Filter Home Assistant logs by `custom_components.ned_energy_weather`.
- **Update** — upgrade using your package manager or replace the component directory and restart. **Remove** — delete the integration entry and Lovelace resource before uninstalling and restarting as prompted. Removing the entry deletes its forecast history.

## Publish on GitHub

The project repository is [vajpeters/ha-ned-energy-weather](https://github.com/vajpeters/ha-ned-energy-weather). To publish to a different empty public repository, update `documentation`, `issue_tracker` and `codeowners` in `custom_components/ned_energy_weather/manifest.json`. Run these commands from the extracted project directory in Git Bash:

```sh
git init -b main
read -r -p "GitHub HTTPS URL: " REPO_URL
git remote add origin "$REPO_URL"
git add .
git commit -m "Initial NED Energieweerbericht release"
git push -u origin main
git tag v0.1.0
git push origin v0.1.0
```

Use **Releases → Draft a new release** to publish tag `v0.1.0`. Keep the card in the integration directory. Default HACS listing has additional requirements including Home Assistant Brands. A public custom repository can be added independently.

## First field test

- Install and complete the config flow with your own valid NED key.
- Compare national and Utrecht solar and wind values with the NED API viewer for matching UTC hours.
- Call the series action for hourly and daily data. Check the response units and Amsterdam day boundaries.
- Open the card with solar and wind selected, change the window and check the future line.
- Change the province and interval. Restart after a snapshot has been saved, then check `historical_forecast` after one forecast hour has passed.

## Sources

- [NED API](https://ned.nl/nl/api) · [Manual](https://ned.nl/nl/handleiding-api) · [Catalog](https://ned.nl/nl/datacatalogus) · [OpenAPI specification](https://api.ned.nl/v1/docs.jsonopenapi)
- [Home Assistant Contributors](https://contributors.home-assistant.io/) · [Marketplace](https://www.home-assistant.io/integrations/marketplace/#custom-repositories) · [HACS integration requirements](https://hacs.dev/docs/publish/integration/)
