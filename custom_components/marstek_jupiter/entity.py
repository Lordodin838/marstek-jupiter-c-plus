"""Gemeinsame Basis aller Entitaeten dieser Integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ADDR_COMM_FIRMWARE,
    ADDR_DEVICE_TYPE,
    ADDR_MAC,
    ADDR_VERSION_BMS,
    ADDR_VERSION_EMS,
    ADDR_VERSION_INV,
    ADDR_VERSION_MPPT,
    DEVICE_TYPES,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import JupiterCoordinator
from .modbus import to_ascii


def _mac_from_registers(coordinator: JupiterCoordinator) -> str | None:
    """MAC aus 0x1100-0x1105, als ASCII-Hex abgelegt.

    12852 = 0x3234 = "24", und so weiter - ergibt 24215ee5674d, also
    exakt die Bluetooth-Adresse aus dem Geraeteeintrag.
    """
    regs = coordinator.data.registers if coordinator.data else {}
    values = [regs.get(ADDR_MAC + i) for i in range(6)]
    if any(v is None for v in values):
        return None
    text = to_ascii([v for v in values if v is not None])
    if len(text) != 12 or not all(c in "0123456789abcdefABCDEF" for c in text):
        return None
    return ":".join(text[i : i + 2] for i in range(0, 12, 2)).lower()


class JupiterEntity(CoordinatorEntity[JupiterCoordinator]):
    """Haengt an einem Geraet und kennt den Block, aus dem sie lebt."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JupiterCoordinator,
        entry_id: str,
        key: str,
        block_keys: tuple[str, ...],
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._key = key
        self._block_keys = block_keys
        self._attr_unique_id = f"{entry_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        regs = self.coordinator.data.registers if self.coordinator.data else {}

        versions = [
            regs.get(a)
            for a in (
                ADDR_VERSION_EMS,
                ADDR_VERSION_BMS,
                ADDR_VERSION_MPPT,
                ADDR_VERSION_INV,
            )
        ]
        sw_version = (
            ".".join(str(v) for v in versions)
            if all(v is not None for v in versions)
            else None
        )

        comm = [regs.get(ADDR_COMM_FIRMWARE + i) for i in range(6)]
        hw_version = (
            to_ascii([v for v in comm if v is not None])
            if all(v is not None for v in comm)
            else None
        )

        model = DEVICE_TYPES.get(regs.get(ADDR_DEVICE_TYPE, -1))

        info = DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            manufacturer=MANUFACTURER,
            name="Marstek Jupiter C+",
            model=model or "Jupiter C+",
            sw_version=sw_version,
            hw_version=hw_version,
            configuration_url=f"http://{self.coordinator.client.host}",
        )
        mac = _mac_from_registers(self.coordinator)
        if mac:
            info["connections"] = {(CONNECTION_NETWORK_MAC, mac)}
        return info

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success or self.coordinator.data is None:
            return False
        return all(
            self.coordinator.data.healthy(key) for key in self._block_keys
        )
