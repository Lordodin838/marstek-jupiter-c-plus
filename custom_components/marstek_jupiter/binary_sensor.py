"""Statusflags des Marstek Jupiter C+ (0x1000-0x100A)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ADDR_STATUS_INVERTER, ADDR_STATUS_PV, block_for_address
from .coordinator import JupiterCoordinator
from .entity import JupiterEntity


@dataclass(frozen=True, kw_only=True)
class JupiterBinaryDescription(BinarySensorEntityDescription):
    address: int
    legacy_unique_id: str | None = None
    legacy_platform: str = "modbus"


BINARY_SENSORS: tuple[JupiterBinaryDescription, ...] = (
    *[
        JupiterBinaryDescription(
            key=f"pv{n + 1}_status",
            translation_key=f"pv{n + 1}_status",
            address=ADDR_STATUS_PV[n],
            device_class=BinarySensorDeviceClass.RUNNING,
            legacy_unique_id=f"jupiter_modbus_pv{n + 1}_status",
        )
        for n in range(4)
    ],
    JupiterBinaryDescription(
        key="inverter_status",
        translation_key="inverter_status",
        address=ADDR_STATUS_INVERTER,
        device_class=BinarySensorDeviceClass.RUNNING,
        legacy_unique_id="jupiter_modbus_inv_status",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: JupiterCoordinator = entry.runtime_data.coordinator
    adopted = entry.runtime_data.adopted_entity_ids
    async_add_entities(
        JupiterBinarySensor(coordinator, entry.entry_id, description, adopted)
        for description in BINARY_SENSORS
    )


class JupiterBinarySensor(JupiterEntity, BinarySensorEntity):
    entity_description: JupiterBinaryDescription

    def __init__(
        self,
        coordinator: JupiterCoordinator,
        entry_id: str,
        description: JupiterBinaryDescription,
        adopted: dict[str, str],
    ) -> None:
        block = block_for_address(description.address)
        super().__init__(
            coordinator,
            entry_id,
            description.key,
            (block,) if block else (),
        )
        self.entity_description = description
        if (previous := adopted.get(description.key)) is not None:
            self.entity_id = previous

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.registers.get(self.entity_description.address)
        # Nebenbefund aus der Registersuche: der Statusblock enthaelt
        # nicht nur 0 und 1 - 0x1001 stand einmal auf 2. Deshalb "ungleich
        # null" statt "gleich eins".
        return None if raw is None else bool(raw)
