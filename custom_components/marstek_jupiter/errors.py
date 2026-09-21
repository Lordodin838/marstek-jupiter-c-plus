"""Fehlercode des Geraets als Reparatur-Meldung und Ereignis.

Steht im Register 0x0011 ein Code ungleich 0, legt die Integration unter
Einstellungen -> Reparaturen eine Meldung mit Klartext an und feuert das
Ereignis ``marstek_jupiter_error``. Geht der Code auf 0 zurueck,
verschwindet die Meldung, und das Ereignis kommt noch einmal mit
``active: false``.

Damit braucht niemand mehr eine eigene Automation, um einen Fehler zu
bemerken. Wer trotzdem benachrichtigt werden will (Push aufs Handy), baut
die Automation auf dem Ereignis auf - das ist stabiler als ein Trigger
auf den Sensorzustand, weil es genau einmal je Aenderung kommt.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import ADDR_ERROR_CODE, DOMAIN, block_for_address, error_text
from .coordinator import JupiterCoordinator

EVENT_ERROR = f"{DOMAIN}_error"
ISSUE_KEY = "device_error"
_ERROR_BLOCK = block_for_address(ADDR_ERROR_CODE)


def issue_id(entry_id: str) -> str:
    return f"{ISSUE_KEY}_{entry_id}"


class ErrorWatcher:
    """Beobachtet den Fehlercode und meldet nur Aenderungen."""

    def __init__(
        self, hass: HomeAssistant, coordinator: JupiterCoordinator, entry_id: str
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._entry_id = entry_id
        # None = noch kein gueltiger Wert gesehen
        self._last: int | None = None

    @callback
    def async_check(self) -> None:
        data = self._coordinator.data
        if data is None or not data.healthy(_ERROR_BLOCK):
            # Ohne frischen Wert nichts entscheiden - weder melden noch
            # eine bestehende Meldung zuruecknehmen.
            return
        code = data.registers.get(ADDR_ERROR_CODE)
        if code is None or code == self._last:
            return

        previous = self._last
        self._last = code

        if code:
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                issue_id(self._entry_id),
                is_fixable=False,
                is_persistent=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=ISSUE_KEY,
                translation_placeholders={
                    "code": str(code),
                    "code_hex": f"0x{code:X}",
                    "text": error_text(code),
                },
            )
        else:
            ir.async_delete_issue(self._hass, DOMAIN, issue_id(self._entry_id))

        # Beim allerersten Wert nach dem Start kein Ereignis, wenn alles in
        # Ordnung ist - sonst kaeme bei jedem Neustart "Fehler behoben".
        if previous is None and not code:
            return
        self._hass.bus.async_fire(
            EVENT_ERROR,
            {
                "entry_id": self._entry_id,
                "active": bool(code),
                "code": code,
                "code_hex": f"0x{code:X}",
                "description": error_text(code),
                "previous_code": previous,
            },
        )
