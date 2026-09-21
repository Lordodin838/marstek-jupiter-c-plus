"""Sensoren des Marstek Jupiter C+."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import (
    ADDR_BATTERY_SOC,
    ADDR_BATTERY_VOLTAGE,
    ADDR_CELL_VOLTAGE_MAX,
    ADDR_CELL_VOLTAGE_MIN,
    ADDR_COMM_FIRMWARE,
    ADDR_DAILY_GENERATION,
    ADDR_DAILY_GRID,
    ADDR_DEVICE_ID,
    ADDR_DEVICE_TYPE,
    ADDR_ERROR_CODE,
    ADDR_GRID_POWER,
    ADDR_MAC,
    ADDR_MONTHLY_GENERATION,
    ADDR_MONTHLY_GRID,
    ADDR_PV_CURRENT,
    ADDR_PV_POWER,
    ADDR_PV_VOLTAGE,
    ADDR_TEMPERATURE,
    ADDR_UNKNOWN_0012,
    ADDR_UNKNOWN_0023,
    ADDR_VERSION_BMS,
    ADDR_VERSION_EMS,
    ADDR_VERSION_INV,
    ADDR_VERSION_MPPT,
    ADDR_VERSION_SCREEN,
    CONF_ERROR_FALLBACK,
    DEVICE_TYPES,
    block_for_address,
    error_text,
)
from .coordinator import (
    ENERGY_CHARGE,
    ENERGY_DISCHARGE,
    ENERGY_PV,
    JupiterCoordinator,
    JupiterData,
)
from .entity import JupiterEntity
from .modbus import to_ascii, to_int16, to_uint32

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class JupiterSensorDescription(SensorEntityDescription):
    """Sensorbeschreibung mit Registerbezug."""

    addresses: tuple[int, ...]
    value_fn: Callable[[JupiterData], StateType]
    # unique_id der bisherigen YAML-Entitaet. Wird beim Einrichten
    # uebernommen, damit Entity-ID, Verlauf und Langzeitstatistik
    # erhalten bleiben.
    legacy_unique_id: str | None = None
    legacy_platform: str = "modbus"


def _raw(address: int) -> Callable[[JupiterData], StateType]:
    return lambda data: data.registers.get(address)


def _scaled(address: int, factor: float, digits: int):
    def _value(data: JupiterData) -> StateType:
        raw = data.registers.get(address)
        return None if raw is None else round(raw * factor, digits)

    return _value


def _signed(address: int):
    def _value(data: JupiterData) -> StateType:
        raw = data.registers.get(address)
        return None if raw is None else to_int16(raw)

    return _value


def _energy(address: int):
    """uint32 ueber zwei Register, hohes Wort zuerst, Faktor 0,01 kWh."""

    def _value(data: JupiterData) -> StateType:
        high = data.registers.get(address)
        low = data.registers.get(address + 1)
        if high is None or low is None:
            return None
        return round(to_uint32(high, low) * 0.01, 2)

    return _value


def _ascii(address: int, count: int = 6):
    def _value(data: JupiterData) -> StateType:
        values = [data.registers.get(address + i) for i in range(count)]
        if any(v is None for v in values):
            return None
        return to_ascii([v for v in values if v is not None]) or None

    return _value


def _total_pv_power(data: JupiterData) -> StateType:
    values = [data.registers.get(a) for a in ADDR_PV_POWER]
    if all(v is None for v in values):
        return None
    return sum(v for v in values if v is not None)


def _battery_power(data: JupiterData) -> StateType:
    """DC-Batterieleistung. Positiv = laden, negativ = entladen.

    Das Geraet liefert dafuer kein Register - 0x000E wurde getestet und
    ist es nicht. Der Wert ergibt sich aus der Bilanz: was aus der PV
    nicht ans Netz geht, geht in die Batterie. Wandlungsverluste (rund
    6 %) sind nicht beruecksichtigt; fuer die Energiebilanz sind die
    Geraetezaehler genauer.

    Anders als bei der frueheren Template-Loesung stammen beide Summanden
    garantiert aus derselben Abfragerunde - PV-Leistungen und
    Netzleistung liegen im selben Leseblock.
    """
    pv = _total_pv_power(data)
    grid = data.registers.get(ADDR_GRID_POWER)
    if pv is None or grid is None:
        return None
    return int(pv) - to_int16(grid)


def _cell_delta(data: JupiterData) -> StateType:
    """Zelldrift in mV.

    Unter 50 mV ist ein gesunder Pack, ueber 100 mV laeuft eine Zelle
    davon - frueher Hinweis auf Alterung, lange bevor die Kapazitaet
    sichtbar nachlaesst.

    Beide Werte kommen jetzt aus derselben Anfrage. Die frueheren kurz
    negativen Differenzen durch den Zeitversatz der beiden Einzelabfragen
    koennen damit nicht mehr entstehen.
    """
    high = data.registers.get(ADDR_CELL_VOLTAGE_MAX)
    low = data.registers.get(ADDR_CELL_VOLTAGE_MIN)
    if high is None or low is None:
        return None
    return high - low


def _device_type_text(data: JupiterData) -> StateType:
    raw = data.registers.get(ADDR_DEVICE_TYPE)
    if raw is None:
        return None
    return DEVICE_TYPES.get(raw, "Unbekannt")


SENSORS: tuple[JupiterSensorDescription, ...] = (
    # --- PV-Eingaenge -------------------------------------------------
    # Spannung und Strom kommen im schnellen Block ohne Zusatzkosten mit;
    # frueher liefen sie auf 121 s, weil jede Einzelabfrage Buslast war.
    *[
        JupiterSensorDescription(
            key=f"pv{n + 1}_voltage",
            translation_key=f"pv{n + 1}_voltage",
            addresses=(ADDR_PV_VOLTAGE[n],),
            value_fn=_scaled(ADDR_PV_VOLTAGE[n], 0.1, 1),
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            legacy_unique_id=f"jupiter_modbus_pv{n + 1}_voltage",
        )
        for n in range(4)
    ],
    *[
        JupiterSensorDescription(
            key=f"pv{n + 1}_current",
            translation_key=f"pv{n + 1}_current",
            addresses=(ADDR_PV_CURRENT[n],),
            value_fn=_scaled(ADDR_PV_CURRENT[n], 0.1, 1),
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            legacy_unique_id=f"jupiter_modbus_pv{n + 1}_current",
        )
        for n in range(4)
    ],
    *[
        JupiterSensorDescription(
            key=f"pv{n + 1}_power",
            translation_key=f"pv{n + 1}_power",
            addresses=(ADDR_PV_POWER[n],),
            value_fn=_raw(ADDR_PV_POWER[n]),
            native_unit_of_measurement=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            legacy_unique_id=f"jupiter_modbus_pv{n + 1}_power",
        )
        for n in range(4)
    ],
    JupiterSensorDescription(
        key="pv_total_power",
        translation_key="pv_total_power",
        addresses=ADDR_PV_POWER,
        value_fn=_total_pv_power,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        legacy_unique_id="jupiter_modbus_total_pv_power",
        legacy_platform="template",
    ),
    # --- Netz und Batterie --------------------------------------------
    JupiterSensorDescription(
        key="grid_power",
        translation_key="grid_power",
        addresses=(ADDR_GRID_POWER,),
        value_fn=_signed(ADDR_GRID_POWER),
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        legacy_unique_id="jupiter_modbus_grid_power",
    ),
    JupiterSensorDescription(
        key="battery_power",
        translation_key="battery_power",
        addresses=(*ADDR_PV_POWER, ADDR_GRID_POWER),
        value_fn=_battery_power,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        legacy_unique_id="jupiter_battery_power_calculated",
        legacy_platform="template",
    ),
    JupiterSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        addresses=(ADDR_BATTERY_VOLTAGE,),
        value_fn=_scaled(ADDR_BATTERY_VOLTAGE, 0.1, 1),
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        legacy_unique_id="jupiter_modbus_battery_voltage",
    ),
    JupiterSensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        addresses=(ADDR_BATTERY_SOC,),
        value_fn=_raw(ADDR_BATTERY_SOC),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        legacy_unique_id="jupiter_modbus_battery_soc",
    ),
    # --- Energiezaehler -----------------------------------------------
    JupiterSensorDescription(
        key="daily_generation",
        translation_key="daily_generation",
        addresses=(ADDR_DAILY_GENERATION, ADDR_DAILY_GENERATION + 1),
        value_fn=_energy(ADDR_DAILY_GENERATION),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        legacy_unique_id="jupiter_modbus_daily_generation",
    ),
    JupiterSensorDescription(
        key="monthly_generation",
        translation_key="monthly_generation",
        addresses=(ADDR_MONTHLY_GENERATION, ADDR_MONTHLY_GENERATION + 1),
        value_fn=_energy(ADDR_MONTHLY_GENERATION),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        legacy_unique_id="jupiter_modbus_monthly_generation",
    ),
    JupiterSensorDescription(
        key="daily_grid",
        translation_key="daily_grid",
        addresses=(ADDR_DAILY_GRID, ADDR_DAILY_GRID + 1),
        value_fn=_energy(ADDR_DAILY_GRID),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        legacy_unique_id="jupiter_modbus_daily_grid",
    ),
    JupiterSensorDescription(
        key="monthly_grid",
        translation_key="monthly_grid",
        addresses=(ADDR_MONTHLY_GRID, ADDR_MONTHLY_GRID + 1),
        value_fn=_energy(ADDR_MONTHLY_GRID),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        legacy_unique_id="jupiter_modbus_monthly_grid",
    ),
    # --- Zellspannungen -------------------------------------------------
    # 0x0020 und 0x0021, durch Registersuche gefunden und in keiner
    # Dokumentation. Beleg: Wert mal 16 Zellen ergibt die Batteriespannung
    # aus 0x000F (3383 -> 54,1 bei gemessenen 54,0).
    # Das ESPHome-Projekt retris83-ger liest dieselben zwei Register und
    # deutet sie als "System Temperatur 1/2" mit Faktor 0,01. Zwei
    # Register, die auf 0,003 identisch sind und dem Ladezustand folgen,
    # sind keine zwei Systemtemperaturen.
    JupiterSensorDescription(
        key="cell_voltage_max",
        translation_key="cell_voltage_max",
        addresses=(ADDR_CELL_VOLTAGE_MAX,),
        value_fn=_scaled(ADDR_CELL_VOLTAGE_MAX, 0.001, 3),
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        legacy_unique_id="jupiter_modbus_cell_voltage_max",
    ),
    JupiterSensorDescription(
        key="cell_voltage_min",
        translation_key="cell_voltage_min",
        addresses=(ADDR_CELL_VOLTAGE_MIN,),
        value_fn=_scaled(ADDR_CELL_VOLTAGE_MIN, 0.001, 3),
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        legacy_unique_id="jupiter_modbus_cell_voltage_min",
    ),
    JupiterSensorDescription(
        key="cell_voltage_delta",
        translation_key="cell_voltage_delta",
        addresses=(ADDR_CELL_VOLTAGE_MAX, ADDR_CELL_VOLTAGE_MIN),
        value_fn=_cell_delta,
        native_unit_of_measurement="mV",
        state_class=SensorStateClass.MEASUREMENT,
        legacy_unique_id="jupiter_cell_voltage_delta",
        legacy_platform="template",
    ),
    # --- Temperatur ------------------------------------------------------
    # 0x000E. Als Leistungswert widerlegt (stand konstant auf 300, waehrend
    # PV zwischen 472 und 493 W lief). Der Tagesverlauf spricht fuer die
    # Innen- beziehungsweise Umgebungstemperatur: glatte Kurve, Minimum vor
    # Sonnenaufgang, Maximum am fruehen Nachmittag, und der Wert folgt der
    # Umgebung statt der Last. "unbestaetigt" bleibt stehen, bis es jemand
    # auf einem zweiten Geraet nachvollzieht.
    JupiterSensorDescription(
        key="temperature",
        translation_key="temperature",
        addresses=(ADDR_TEMPERATURE,),
        value_fn=_scaled(ADDR_TEMPERATURE, 0.1, 1),
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        legacy_unique_id="jupiter_temperature_filtered",
        legacy_platform="template",
    ),
    JupiterSensorDescription(
        key="temperature_raw",
        translation_key="temperature_raw",
        addresses=(ADDR_TEMPERATURE,),
        value_fn=_scaled(ADDR_TEMPERATURE, 0.1, 1),
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        legacy_unique_id="jupiter_modbus_temperature_suspected",
    ),
    # --- Fehlercode -------------------------------------------------------
    # 0x0011 am 18.09.2026 identifiziert: hm2mqtt meldete dreimal Fehler
    # 426, das Register stand in denselben Fenstern auf 1062 = 0x426.
    # Vier von vier Abfragen stimmten ueberein.
    # Damit ist die ESPHome-Deutung "0x0011 = Batteriestrom" widerlegt.
    JupiterSensorDescription(
        key="error_code",
        translation_key="error_code",
        addresses=(ADDR_ERROR_CODE,),
        value_fn=_raw(ADDR_ERROR_CODE),
        entity_category=EntityCategory.DIAGNOSTIC,
        legacy_unique_id="jupiter_diag_0011",
    ),
    # --- Versionen und Geraeteinfo ---------------------------------------
    JupiterSensorDescription(
        key="device_id",
        translation_key="device_id",
        addresses=(ADDR_DEVICE_ID,),
        value_fn=_raw(ADDR_DEVICE_ID),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        legacy_unique_id="jupiter_modbus_device_id",
    ),
    JupiterSensorDescription(
        key="ems_version",
        translation_key="ems_version",
        addresses=(ADDR_VERSION_EMS,),
        value_fn=_raw(ADDR_VERSION_EMS),
        entity_category=EntityCategory.DIAGNOSTIC,
        legacy_unique_id="jupiter_modbus_ems_version",
    ),
    JupiterSensorDescription(
        key="inv_version",
        translation_key="inv_version",
        addresses=(ADDR_VERSION_INV,),
        value_fn=_raw(ADDR_VERSION_INV),
        entity_category=EntityCategory.DIAGNOSTIC,
        legacy_unique_id="jupiter_modbus_inv_version",
    ),
    JupiterSensorDescription(
        key="mppt_version",
        translation_key="mppt_version",
        addresses=(ADDR_VERSION_MPPT,),
        value_fn=_raw(ADDR_VERSION_MPPT),
        entity_category=EntityCategory.DIAGNOSTIC,
        legacy_unique_id="jupiter_modbus_mppt_version",
    ),
    JupiterSensorDescription(
        key="bms_version",
        translation_key="bms_version",
        addresses=(ADDR_VERSION_BMS,),
        value_fn=_raw(ADDR_VERSION_BMS),
        entity_category=EntityCategory.DIAGNOSTIC,
        legacy_unique_id="jupiter_modbus_bms_version",
    ),
    JupiterSensorDescription(
        key="screen_version",
        translation_key="screen_version",
        addresses=(ADDR_VERSION_SCREEN,),
        value_fn=_raw(ADDR_VERSION_SCREEN),
        entity_category=EntityCategory.DIAGNOSTIC,
        legacy_unique_id="jupiter_modbus_screen_version",
    ),
    JupiterSensorDescription(
        key="device_type",
        translation_key="device_type",
        addresses=(ADDR_DEVICE_TYPE,),
        value_fn=_raw(ADDR_DEVICE_TYPE),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        legacy_unique_id="jupiter_modbus_device_type",
    ),
    JupiterSensorDescription(
        key="device_type_text",
        translation_key="device_type_text",
        addresses=(ADDR_DEVICE_TYPE,),
        value_fn=_device_type_text,
        entity_category=EntityCategory.DIAGNOSTIC,
        legacy_unique_id="jupiter_modbus_device_type_text",
        legacy_platform="template",
    ),
    # 0x1100-0x1105 und 0x1200-0x1205, am 18.09.2026 durch die Grobsuche
    # gefunden und in der Community-Registerkarte nicht vorhanden. Die
    # MAC deckt sich mit der Bluetooth-Adresse aus dem Geraeteeintrag;
    # die Modul-Firmware ist ein Build-Stempel JJJJMMTTHHMM.
    JupiterSensorDescription(
        key="mac_address",
        translation_key="mac_address",
        addresses=tuple(ADDR_MAC + i for i in range(6)),
        value_fn=_ascii(ADDR_MAC),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        legacy_unique_id="jupiter_modbus_mac",
    ),
    JupiterSensorDescription(
        key="comm_firmware",
        translation_key="comm_firmware",
        addresses=tuple(ADDR_COMM_FIRMWARE + i for i in range(6)),
        value_fn=_ascii(ADDR_COMM_FIRMWARE),
        entity_category=EntityCategory.DIAGNOSTIC,
        legacy_unique_id="jupiter_modbus_comm_version",
    ),
    # --- Verbliebene unbekannte Register ---------------------------------
    # 0x0012: konstant 0 ueber Tage, liegt neben dem Fehlercode und blieb
    #         wie der MQTT-Alarmcode unbewegt - konsistent mit "Alarmcode",
    #         aber unbewiesen, weil nie ein Alarm kam.
    # 0x0023: 36 bis 39, engbandig, sprang beim Firmware-Update von ~51
    #         auf ~37. Als Strom, Spannung und SoC widerlegt.
    # 0x0024 wird nicht mehr ausgewertet (vier Tage konstant 0), kommt im
    # Block aber ohnehin mit.
    JupiterSensorDescription(
        key="diag_0012",
        translation_key="diag_0012",
        addresses=(ADDR_UNKNOWN_0012,),
        value_fn=_signed(ADDR_UNKNOWN_0012),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        legacy_unique_id="jupiter_diag_0012",
    ),
    JupiterSensorDescription(
        key="diag_0023",
        translation_key="diag_0023",
        addresses=(ADDR_UNKNOWN_0023,),
        value_fn=_raw(ADDR_UNKNOWN_0023),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        legacy_unique_id="jupiter_diag_0023",
    ),
    # Die uebrigen Statusflags. Sie kommen im Statusblock ohnehin mit und
    # kosten nichts extra; standardmaessig abgeschaltet, weil ihre
    # Bedeutung nicht geklaert ist. Wer weitersuchen will, schaltet sie
    # ein. 0x1001 stand einmal auf 2 - der Block enthaelt also nicht nur
    # 0 und 1, deshalb hier als Zahl und nicht als Ja/Nein.
    *[
        JupiterSensorDescription(
            key=f"status_{addr:04x}",
            name=f"Status 0x{addr:04X}",
            addresses=(addr,),
            value_fn=_raw(addr),
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        )
        for addr in (0x1000, 0x1001, 0x1002, 0x1003, 0x1009, 0x100A)
    ],
)


@dataclass(frozen=True, kw_only=True)
class JupiterEnergyDescription(SensorEntityDescription):
    """Energiezaehler, von der Integration selbst aufsummiert."""

    addresses: tuple[int, ...]


# Aufsummierte Energie fuer das Energie-Dashboard. Ersetzt die sonst
# noetigen Riemann-Helfer ("Integral") auf PV- und Batterieleistung.
# Der Coordinator summiert nur Runden, in denen die Leistungen frisch
# gelesen wurden; Ausfaelle werden nicht hochgerechnet.
ENERGY_SENSORS: tuple[JupiterEnergyDescription, ...] = (
    JupiterEnergyDescription(
        key=ENERGY_PV,
        translation_key=ENERGY_PV,
        addresses=ADDR_PV_POWER,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
    ),
    JupiterEnergyDescription(
        key=ENERGY_CHARGE,
        translation_key=ENERGY_CHARGE,
        addresses=(*ADDR_PV_POWER, ADDR_GRID_POWER),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
    ),
    JupiterEnergyDescription(
        key=ENERGY_DISCHARGE,
        translation_key=ENERGY_DISCHARGE,
        addresses=(*ADDR_PV_POWER, ADDR_GRID_POWER),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
    ),
)


def blocks_for(addresses: tuple[int, ...]) -> tuple[str, ...]:
    keys = {block_for_address(a) for a in addresses}
    return tuple(sorted(k for k in keys if k is not None))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Sensoren einrichten."""
    coordinator: JupiterCoordinator = entry.runtime_data.coordinator
    adopted: dict[str, str] = entry.runtime_data.adopted_entity_ids

    entities: list[SensorEntity] = [
        JupiterSensor(coordinator, entry.entry_id, description, adopted)
        for description in SENSORS
    ]
    entities.append(JupiterErrorTextSensor(coordinator, entry, adopted))
    entities.extend(
        JupiterEnergySensor(coordinator, entry.entry_id, description)
        for description in ENERGY_SENSORS
    )
    async_add_entities(entities)


class JupiterSensor(JupiterEntity, SensorEntity):
    """Ein Registerwert als Sensor."""

    entity_description: JupiterSensorDescription

    def __init__(
        self,
        coordinator: JupiterCoordinator,
        entry_id: str,
        description: JupiterSensorDescription,
        adopted: dict[str, str],
    ) -> None:
        super().__init__(
            coordinator,
            entry_id,
            description.key,
            blocks_for(description.addresses),
        )
        self.entity_description = description
        # Die frueher vergebene Entity-ID uebernehmen, damit Verlauf,
        # Statistik, Dashboards und Automationen weiterlaufen.
        if (previous := adopted.get(description.key)) is not None:
            self.entity_id = previous

    @property
    def native_value(self) -> StateType:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class JupiterEnergySensor(JupiterEntity, RestoreSensor):
    """Energiezaehler, der einen Neustart ueberlebt.

    Stand = zuletzt gespeicherter Wert + was der Coordinator seit dem
    Start aufsummiert hat. Home Assistant speichert den letzten Zustand
    selbst (RestoreSensor); verloren gehen bei einem Neustart hoechstens
    die Sekunden seit der letzten Aktualisierung.
    """

    entity_description: JupiterEnergyDescription

    def __init__(
        self,
        coordinator: JupiterCoordinator,
        entry_id: str,
        description: JupiterEnergyDescription,
    ) -> None:
        super().__init__(
            coordinator,
            entry_id,
            description.key,
            blocks_for(description.addresses),
        )
        self.entity_description = description
        self._base = 0.0
        # Was der Coordinator beim Wiederherstellen schon gezaehlt hatte.
        # Nach einem Neuladen der Integration beginnt er wieder bei 0,
        # der Sensor aber bleibt dieselbe Instanz nicht - deshalb der
        # Abzug, damit nichts doppelt zaehlt.
        self._offset = 0.0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            try:
                self._base = float(last.native_value)
            except (TypeError, ValueError):
                self._base = 0.0
        data = self.coordinator.data
        if data is not None:
            self._offset = data.energy.get(self.entity_description.key, 0.0)

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None:
            return round(self._base, 3)
        counted = data.energy.get(self.entity_description.key, 0.0)
        return round(self._base + counted - self._offset, 3)


class JupiterErrorTextSensor(JupiterEntity, SensorEntity):
    """Fehlercode im Klartext, mit optionaler zweiter Quelle.

    Vorrang hat das Modbus-Register: lokal, live und unabhaengig von der
    Marstek-Cloud. Steht es auf 0 und ist ein MQTT-Fehlersensor
    hinterlegt, wird dessen Wert genommen - MQTT haelt einen Code laenger,
    ein sehr kurzer Fehler kann im Register zwischen zwei Abfragen
    durchrutschen.
    """

    _attr_translation_key = "error_text"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(
        self,
        coordinator: JupiterCoordinator,
        entry: ConfigEntry,
        adopted: dict[str, str],
    ) -> None:
        super().__init__(
            coordinator, entry.entry_id, "error_text", blocks_for((ADDR_ERROR_CODE,))
        )
        self._fallback_entity: str | None = entry.options.get(
            CONF_ERROR_FALLBACK
        ) or entry.data.get(CONF_ERROR_FALLBACK)
        if (previous := adopted.get("error_text")) is not None:
            self.entity_id = previous

    @property
    def native_value(self) -> StateType:
        if self.coordinator.data is None:
            return None
        code = self.coordinator.data.registers.get(ADDR_ERROR_CODE)
        if code is None:
            return None
        if not code and self._fallback_entity:
            state = self.hass.states.get(self._fallback_entity)
            if state is not None and state.state not in (
                "unknown",
                "unavailable",
                "",
            ):
                try:
                    code = int(float(state.state))
                except (TypeError, ValueError):
                    code = 0
        return error_text(int(code))

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        registers = (
            self.coordinator.data.registers if self.coordinator.data else {}
        )
        raw = registers.get(ADDR_ERROR_CODE)
        return {
            "modbus_code": raw,
            "modbus_code_hex": None if raw is None else f"0x{raw:X}",
            "fallback_entity": self._fallback_entity,
        }
