from dataclasses import dataclass
from enum import StrEnum

@dataclass(frozen=True, kw_only=True)
class EntityDescription:
    key: str
    name: str | None = None
    translation_key: str | None = None
    icon: str | None = None
    entity_category: object = None
    entity_registry_enabled_default: bool = True

@dataclass(frozen=True, kw_only=True)
class SensorEntityDescription(EntityDescription):
    device_class: object = None
    state_class: object = None
    native_unit_of_measurement: str | None = None
    suggested_display_precision: int | None = None

class SensorDeviceClass(StrEnum):
    POWER = "power"
    ENERGY = "energy"
    VOLTAGE = "voltage"
    CURRENT = "current"
    BATTERY = "battery"
    TEMPERATURE = "temperature"

class SensorStateClass(StrEnum):
    MEASUREMENT = "measurement"
    TOTAL_INCREASING = "total_increasing"

class SensorEntity:
    entity_id = None
    hass = None

class RestoreSensor(SensorEntity):
    _last_sensor_data = None
    async def async_added_to_hass(self):
        pass
    async def async_get_last_sensor_data(self):
        return self._last_sensor_data
