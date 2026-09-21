"""Gestaffelte Abfrage des Jupiter C+.

Ein Coordinator, ein Socket, ein Lock. Der schnelle Takt gibt den Rhythmus
vor; langsamere Bloecke haengen sich ein, wenn sie faellig sind. Dadurch
liegt nie mehr als eine Anfrage auf dem Bus, und die regelungsrelevanten
Werte stammen aus demselben Augenblick.

Zum Vergleich: die urspruengliche YAML-Loesung mit Einzelregistern kam auf
rund 48 Anfragen je Minute, diese hier auf rund 15 - bei feinerer
Aufloesung, weil PV-Spannungen und -Stroeme im schnellen Block ohne
Zusatzkosten mitkommen.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from datetime import timedelta

from .const import (
    BLOCKS,
    FAILURES_BEFORE_UNAVAILABLE,
    GRID_POWER_LIMIT,
    TIER_FAST,
    TIER_SLOW,
    TIER_STATIC,
    TIER_STATUS,
    VALID_RANGES,
    ADDR_GRID_POWER,
    ADDR_PV_POWER,
    ENERGY_MAX_GAP,
)
from .modbus import (
    JupiterModbusClient,
    ModbusError,
    ModbusExceptionResponse,
    to_int16,
)

_LOGGER = logging.getLogger(__name__)

ENERGY_PV = "pv_energy"
ENERGY_CHARGE = "battery_charge_energy"
ENERGY_DISCHARGE = "battery_discharge_energy"
ENERGY_KEYS = (ENERGY_PV, ENERGY_CHARGE, ENERGY_DISCHARGE)

# Beide schnellen Bloecke muessen in derselben Runde frisch gelesen sein:
# die PV-Leistungen verteilen sich auf beide, die Netzleistung liegt im
# zweiten.
_ENERGY_BLOCKS = ("fast_a", "fast_b")


@dataclass
class BlockState:
    """Zustand eines Leseblocks."""

    last_success: float = 0.0
    last_attempt: float = 0.0
    failures: int = 0
    exception_code: int | None = None

    @property
    def healthy(self) -> bool:
        return self.failures < FAILURES_BEFORE_UNAVAILABLE and self.last_success > 0


@dataclass
class JupiterData:
    """Was der Coordinator an die Entitaeten weitergibt."""

    registers: dict[int, int] = field(default_factory=dict)
    blocks: dict[str, BlockState] = field(default_factory=dict)
    rejected: int = 0
    requests: int = 0
    # Seit dem Start aufsummierte Energie in kWh, je Zaehler. Die Sensoren
    # addieren das auf ihren zuletzt gespeicherten Stand.
    energy: dict[str, float] = field(
        default_factory=lambda: {key: 0.0 for key in ENERGY_KEYS}
    )

    def healthy(self, block_key: str | None) -> bool:
        if block_key is None:
            return False
        state = self.blocks.get(block_key)
        return bool(state and state.healthy)


class JupiterCoordinator(DataUpdateCoordinator[JupiterData]):
    """Liest den Jupiter blockweise und gestaffelt."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: JupiterModbusClient,
        *,
        config_entry,
        fast_interval: int,
        slow_interval: int,
        status_interval: int,
        static_interval: int,
        entry_title: str,
    ) -> None:
        self.client = client
        self._intervals = {
            TIER_FAST: fast_interval,
            TIER_SLOW: slow_interval,
            TIER_STATUS: status_interval,
            TIER_STATIC: static_interval,
        }
        self._data = JupiterData(
            blocks={block.key: BlockState() for block in BLOCKS}
        )

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=entry_title,
            update_interval=timedelta(seconds=fast_interval),
            # always_update MUSS True bleiben (Standard). Der Coordinator
            # gibt bei jeder Runde dasselbe, veraenderte JupiterData-Objekt
            # zurueck. Mit always_update=False vergleicht Home Assistant
            # alte und neue Daten - das ist dasselbe Objekt, also "gleich",
            # und die Entitaeten werden nie benachrichtigt: sie zeigen nur
            # den Wert vom Start und stehen danach still. So geschehen in
            # 1.0.0. Parallele Durchlaeufe verhindert Home Assistant
            # ohnehin selbst.
            always_update=True,
        )
        self._energy_max_gap = max(ENERGY_MAX_GAP, 3 * fast_interval)
        # (Zeitpunkt, PV-Leistung W, Batterieleistung W) der letzten
        # frischen Messung
        self._last_power: tuple[float, float, float] | None = None

    async def _async_update_data(self) -> JupiterData:
        now = time.monotonic()
        data = self._data
        fatal: Exception | None = None

        for block in BLOCKS:
            state = data.blocks[block.key]
            interval = self._intervals[block.tier]

            # Der schnelle Block laeuft immer mit; die anderen nur, wenn
            # ihr Takt abgelaufen ist. Kleine Toleranz, damit ein Block
            # nicht wegen Millisekunden eine Runde aussetzt.
            if block.tier != TIER_FAST and state.last_attempt:
                if now - state.last_attempt < interval - 0.5:
                    continue

            state.last_attempt = now
            try:
                values = await self.client.read_holding(block.start, block.count)
            except ModbusExceptionResponse as err:
                # Eine Exception ist eine Auskunft des Geraets. Sie
                # bedeutet meist, dass die Registerkarte nicht mehr zur
                # Firmware passt - protokollieren, nicht wiederholen.
                state.failures += 1
                state.exception_code = err.code
                _LOGGER.warning(
                    "Block %s (0x%04X-0x%04X) abgelehnt: Modbus-Exception %d. "
                    "Bei geaenderter Firmware die Registerkarte pruefen.",
                    block.key, block.start, block.end, err.code,
                )
                continue
            except ModbusError as err:
                state.failures += 1
                state.exception_code = None
                level = (
                    logging.WARNING
                    if state.failures == FAILURES_BEFORE_UNAVAILABLE
                    else logging.DEBUG
                )
                _LOGGER.log(
                    level,
                    "Block %s (0x%04X-0x%04X) nicht gelesen (%d. Fehlversuch): %s",
                    block.key, block.start, block.end, state.failures, err,
                )
                if not block.optional:
                    fatal = err
                continue

            data.requests += 1
            state.failures = 0
            state.exception_code = None
            state.last_success = now
            data.rejected += self._store(data, block.start, values)

        # Nur wenn seit dem Start noch nie ein Pflichtblock ankam, gilt die
        # Aktualisierung als gescheitert. Danach halten die Blockzustaende
        # die Verfuegbarkeit der einzelnen Entitaeten - ein kurzer
        # Aussetzer beim Statusblock soll nicht die SoC-Anzeige umwerfen.
        if fatal is not None and not any(
            s.last_success for s in data.blocks.values()
        ):
            raise fatal

        self._integrate_energy(data, now)
        return data

    def _integrate_energy(self, data: JupiterData, now: float) -> None:
        """Leistung zu Energie aufsummieren (Trapezregel).

        Nur Runden, in denen beide schnellen Bloecke frisch gelesen
        wurden, zaehlen. Nach einem Fehlversuch stehen in ``registers``
        noch die alten Werte - die duerfen nicht weiter aufaddiert werden.

        Die Batterieleistung ist wie beim Sensor "Batterieleistung
        (berechnet)" die Bilanz PV minus Netzleistung. Geladen und
        entladen werden getrennt gezaehlt, jeweils nur der passende
        Anteil. Wandlungsverluste (rund 6 %) stecken damit im Wert
        "geladen" - fuer das Energie-Dashboard gut genug, fuer eine
        genaue Bilanz sind die Geraetezaehler besser.
        """
        if not all(
            data.blocks[key].last_success == now for key in _ENERGY_BLOCKS
        ):
            return

        pv_values = [data.registers.get(a) for a in ADDR_PV_POWER]
        grid_raw = data.registers.get(ADDR_GRID_POWER)
        if any(v is None for v in pv_values) or grid_raw is None:
            self._last_power = None
            return
        pv = float(sum(v for v in pv_values if v is not None))
        battery = pv - to_int16(grid_raw)

        previous = self._last_power
        self._last_power = (now, pv, battery)
        if previous is None:
            return

        seconds = now - previous[0]
        if seconds <= 0 or seconds > self._energy_max_gap:
            # Zu lange Luecke: neu ansetzen statt hochrechnen.
            _LOGGER.debug(
                "Energiezaehler: Luecke von %.0f s nicht ueberbrueckt", seconds
            )
            return

        hours = seconds / 3600
        data.energy[ENERGY_PV] += (previous[1] + pv) / 2 * hours / 1000
        data.energy[ENERGY_CHARGE] += (
            (max(previous[2], 0.0) + max(battery, 0.0)) / 2 * hours / 1000
        )
        data.energy[ENERGY_DISCHARGE] += (
            (max(-previous[2], 0.0) + max(-battery, 0.0)) / 2 * hours / 1000
        )

    def _store(self, data: JupiterData, start: int, values: list[int]) -> int:
        """Uebernimmt Rohwerte und verwirft Unplausibles.

        Rueckgabe: Anzahl verworfener Register.
        """
        rejected = 0
        for offset, raw in enumerate(values):
            address = start + offset

            if address == ADDR_GRID_POWER:
                # Vorzeichenbehaftet. Die verbreitete Community-Karte
                # fuehrt 0x000D als unsigned - als uint16 erschiene ein
                # Netzbezug als rund 65000 W und wuerde jede
                # Hausverbrauchs-Rechnung zerlegen.
                if abs(to_int16(raw)) > GRID_POWER_LIMIT:
                    rejected += 1
                    continue
                data.registers[address] = raw
                continue

            limits = VALID_RANGES.get(address)
            if limits is not None and not limits[0] <= raw <= limits[1]:
                rejected += 1
                _LOGGER.debug(
                    "0x%04X: Rohwert %d ausserhalb %s - verworfen, "
                    "letzter guter Wert bleibt stehen",
                    address, raw, limits,
                )
                continue

            data.registers[address] = raw
        return rejected
