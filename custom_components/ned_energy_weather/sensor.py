"""Current utilization sensors and update diagnostics."""

from datetime import UTC, datetime, timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, PROVINCES, UNITS

CLASSES = {
    "capacity": SensorDeviceClass.POWER,
    "volume": SensorDeviceClass.ENERGY,
    "emission": SensorDeviceClass.WEIGHT,
}
DESCRIPTIONS = {
    key: SensorEntityDescription(
        key=key,
        name=key.replace("_", " ").capitalize(),
        native_unit_of_measurement=unit,
        device_class=CLASSES.get(key),
        state_class=SensorStateClass.MEASUREMENT if key != "volume" else None,
        entity_registry_enabled_default=key == "capacity",
    )
    for key, unit in UNITS.items()
}


def unique_id(point: int, type_id: int, activity: int, field: str) -> str:
    return f"{point}_{type_id}_{activity}_{field}"


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        [
            NedSensor(coordinator, point, item, DESCRIPTIONS[field])
            for point, item in coordinator.datasets
            for field in item.fields
        ]
        + [NedStatus(coordinator)]
    )


class NedSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, point, item, description):
        super().__init__(coordinator)
        self.key = (point, item.type_id, item.activity)
        self.index = tuple(UNITS).index(description.key)
        self.entity_description = description
        self._attr_unique_id = unique_id(*self.key, description.key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{point}_{item.type_id}_{item.activity}")},
            name=f"NED {item.name} {PROVINCES.get(point, 'Nederland')}",
            manufacturer="Nationaal Energie Dashboard",
        )

    @property
    def available(self) -> bool:
        row = self.coordinator.data.get(self.key)
        return (
            super().available
            and self.key not in self.coordinator.stale
            and row is not None
            and row.valid_to > datetime.now(UTC) - timedelta(hours=12)
            and row.values[self.index] is not None
        )

    @property
    def native_value(self):
        row = self.coordinator.data.get(self.key)
        return row.values[self.index] if row else None


class NedStatus(CoordinatorEntity, SensorEntity):
    _attr_name = "NED Last successful update"
    _attr_unique_id = "last_successful_update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self):
        return self.coordinator.last_success is not None

    @property
    def native_value(self):
        return self.coordinator.last_success

    @property
    def extra_state_attributes(self):
        return {"api_available": self.coordinator.api_available}
