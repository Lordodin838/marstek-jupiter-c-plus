"""Diagnosedaten zum Herunterladen.

Enthaelt den kompletten Registerabzug des letzten Durchlaufs und den
Zustand jedes Leseblocks - genau das, was bei einer Stoerungssuche oder
nach einem Firmware-Update gebraucht wird.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import BLOCKS


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data

    return {
        "konfiguration": {
            # Host wird bewusst weggelassen - eine lokale IP gehoert nicht
            # in eine Datei, die in ein oeffentliches Issue wandert.
            "host_gesetzt": bool(entry.data.get(CONF_HOST)),
            "optionen": dict(entry.options),
        },
        "bloecke": {
            block.key: {
                "bereich": f"0x{block.start:04X}-0x{block.end:04X}",
                "takt": block.tier,
                "fehlversuche": data.blocks[block.key].failures if data else None,
                "letzter_erfolg": (
                    data.blocks[block.key].last_success if data else None
                ),
                "exception": (
                    data.blocks[block.key].exception_code if data else None
                ),
            }
            for block in BLOCKS
        },
        "register": (
            {f"0x{addr:04X}": value for addr, value in sorted(data.registers.items())}
            if data
            else {}
        ),
        "verworfene_werte": data.rejected if data else None,
        "anfragen_gesamt": data.requests if data else None,
        "uebernommene_entity_ids": entry.runtime_data.adopted_entity_ids,
    }
