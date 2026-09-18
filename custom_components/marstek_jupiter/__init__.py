"""Marstek Jupiter C+ ueber Modbus TCP."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_ADOPT_LEGACY,
    CONF_FAST_INTERVAL,
    CONF_MESSAGE_WAIT,
    CONF_SLOW_INTERVAL,
    CONF_STATUS_INTERVAL,
    CONF_TIMEOUT,
    CONF_UNIT_ID,
    DEFAULT_FAST_INTERVAL,
    DEFAULT_MESSAGE_WAIT,
    DEFAULT_PORT,
    DEFAULT_SLOW_INTERVAL,
    DEFAULT_STATIC_INTERVAL,
    DEFAULT_STATUS_INTERVAL,
    DEFAULT_TIMEOUT,
    DEFAULT_UNIT_ID,
)
from .coordinator import JupiterCoordinator
from .modbus import JupiterModbusClient
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


@dataclass
class JupiterRuntime:
    coordinator: JupiterCoordinator
    # key der Entitaet -> bisherige entity_id, die uebernommen wird
    adopted_entity_ids: dict[str, str] = field(default_factory=dict)


JupiterConfigEntry = ConfigEntry


def _option(entry: ConfigEntry, key: str, default):
    return entry.options.get(key, entry.data.get(key, default))


async def async_setup_entry(hass: HomeAssistant, entry: JupiterConfigEntry) -> bool:
    client = JupiterModbusClient(
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        unit_id=entry.data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID),
        timeout=_option(entry, CONF_TIMEOUT, DEFAULT_TIMEOUT),
        message_wait=_option(entry, CONF_MESSAGE_WAIT, DEFAULT_MESSAGE_WAIT),
    )

    coordinator = JupiterCoordinator(
        hass,
        client,
        config_entry=entry,
        fast_interval=_option(entry, CONF_FAST_INTERVAL, DEFAULT_FAST_INTERVAL),
        slow_interval=_option(entry, CONF_SLOW_INTERVAL, DEFAULT_SLOW_INTERVAL),
        status_interval=_option(entry, CONF_STATUS_INTERVAL, DEFAULT_STATUS_INTERVAL),
        static_interval=DEFAULT_STATIC_INTERVAL,
        entry_title=entry.title,
    )

    adopted: dict[str, str] = {}
    if _option(entry, CONF_ADOPT_LEGACY, True):
        adopted = _adopt_legacy_entities(hass)

    entry.runtime_data = JupiterRuntime(
        coordinator=coordinator, adopted_entity_ids=adopted
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.close()
        raise

    if not coordinator.data or not coordinator.data.registers:
        await client.close()
        raise ConfigEntryNotReady("Keine Registerwerte gelesen")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    async_setup_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: JupiterConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.coordinator.client.close()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: JupiterConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _legacy_map() -> dict[tuple[str, str, str], str]:
    """(Plattform, Domain, alte unique_id) -> Schluessel der neuen Entitaet."""
    # Import hier, damit die Plattformmodule nicht beim Laden der
    # Integration schon gezogen werden.
    from .binary_sensor import BINARY_SENSORS
    from .sensor import SENSORS

    mapping: dict[tuple[str, str, str], str] = {}
    for description in SENSORS:
        if description.legacy_unique_id:
            mapping[
                (description.legacy_platform, "sensor", description.legacy_unique_id)
            ] = description.key
    for description in BINARY_SENSORS:
        if description.legacy_unique_id:
            mapping[
                (
                    description.legacy_platform,
                    "binary_sensor",
                    description.legacy_unique_id,
                )
            ] = description.key
    # Der Klartext-Fehlersensor hat keine Beschreibung in SENSORS.
    mapping[("template", "sensor", "jupiter_error_code_text")] = "error_text"
    return mapping


def _adopt_legacy_entities(hass: HomeAssistant) -> dict[str, str]:
    """Bisherige Entity-IDs uebernehmen.

    Die alte YAML-Loesung legte ihre Entitaeten unter den Plattformen
    ``modbus`` und ``template`` an. Deren Registrierungseintraege werden
    hier entfernt und ihre Entity-IDs gemerkt; die neuen Entitaeten
    melden sich dann mit genau diesen IDs an.

    Warum das wichtig ist: Verlauf und Langzeitstatistik haengen an der
    Entity-ID, nicht an der unique_id. Ohne diesen Schritt haette jede
    Entitaet eine neue ID mit Anhaengsel "_2", und Dashboards, Helfer,
    Templates und Automationen zeigten ins Leere.

    Voraussetzung: das alte YAML-Paket ist bereits entfernt und Home
    Assistant neu gestartet. Ist es noch aktiv, wird hier nichts
    uebernommen - dann belegen die alten Entitaeten ihre IDs noch selbst.
    """
    registry = er.async_get(hass)
    mapping = _legacy_map()
    adopted: dict[str, str] = {}
    blocked: list[str] = []

    for (platform, domain, unique_id), key in mapping.items():
        entry_id = registry.async_get_entity_id(domain, platform, unique_id)
        if entry_id is None:
            continue

        registry_entry = registry.async_get(entry_id)
        if registry_entry is None:
            continue

        if registry_entry.config_entry_id is not None or not _is_orphaned(
            hass, entry_id
        ):
            # Die alte Entitaet lebt noch. Nicht anfassen - sonst haetten
            # zwei Integrationen dasselbe Geraet im Zugriff und beide
            # wuerden pollen.
            blocked.append(entry_id)
            continue

        adopted[key] = entry_id
        registry.async_remove(entry_id)

    if blocked:
        _LOGGER.warning(
            "%d bisherige Entitaeten sind noch aktiv (z. B. %s). Das alte "
            "YAML-Paket scheint noch geladen zu sein - erst entfernen und "
            "Home Assistant neu starten, sonst pollen zwei Integrationen "
            "dasselbe Geraet und die neuen Entitaeten bekommen IDs mit "
            "Anhaengsel _2.",
            len(blocked),
            ", ".join(sorted(blocked)[:3]),
        )
    if adopted:
        _LOGGER.info(
            "%d bisherige Entity-IDs uebernommen - Verlauf und Statistik "
            "bleiben erhalten.",
            len(adopted),
        )
    return adopted


def _is_orphaned(hass: HomeAssistant, entity_id: str) -> bool:
    """True, wenn zu der Registrierung gerade kein Zustand existiert.

    Eine YAML-Entitaet, deren Paket entfernt wurde, bleibt als
    Registrierungseintrag zurueck, hat aber keinen Zustand mehr. Genau
    diese - und nur diese - duerfen uebernommen werden.
    """
    state = hass.states.get(entity_id)
    return state is None or state.state == "unavailable"
