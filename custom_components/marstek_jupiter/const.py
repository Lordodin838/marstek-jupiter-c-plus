"""Konstanten und Registerkarte fuer den Marstek Jupiter C+.

Die Registerkarte hier ist am realen Geraet erarbeitet worden
(Firmware 142.37.213.110, Geraetetyp 0 = Jupiter C 800 W). Wo sie von
der verbreiteten Community-Karte abweicht, steht der Grund dabei.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "marstek_jupiter"
MANUFACTURER: Final = "Marstek"

CONF_UNIT_ID: Final = "unit_id"
CONF_FAST_INTERVAL: Final = "fast_interval"
CONF_SLOW_INTERVAL: Final = "slow_interval"
CONF_STATUS_INTERVAL: Final = "status_interval"
CONF_TIMEOUT: Final = "timeout"
CONF_MESSAGE_WAIT: Final = "message_wait"
CONF_ADOPT_LEGACY: Final = "adopt_legacy"
CONF_ERROR_FALLBACK: Final = "error_fallback_entity"

DEFAULT_PORT: Final = 502
DEFAULT_UNIT_ID: Final = 1
DEFAULT_FAST_INTERVAL: Final = 10
DEFAULT_SLOW_INTERVAL: Final = 60
DEFAULT_STATUS_INTERVAL: Final = 300
DEFAULT_STATIC_INTERVAL: Final = 3600
DEFAULT_TIMEOUT: Final = 5.0
DEFAULT_MESSAGE_WAIT: Final = 0.15

# Nach so vielen erfolglosen Anlaeufen gilt ein Block als ausgefallen und
# seine Entitaeten werden "nicht verfuegbar". Ein einzelner Fehlversuch
# soll noch keine Luecke im Verlauf reissen.
FAILURES_BEFORE_UNAVAILABLE: Final = 3

TIER_FAST: Final = "fast"
TIER_SLOW: Final = "slow"
TIER_STATUS: Final = "status"
TIER_STATIC: Final = "static"


class Block:
    """Ein Leseblock. Hoechstens 8 Register, siehe modbus.MAX_REGISTERS."""

    __slots__ = ("key", "start", "count", "tier", "optional")

    def __init__(
        self,
        key: str,
        start: int,
        count: int,
        tier: str,
        optional: bool = False,
    ) -> None:
        self.key = key
        self.start = start
        self.count = count
        self.tier = tier
        # optional = faellt der Block aus, laeuft der Rest weiter. Fuer
        # die ASCII-Bloecke gedacht, deren abweichende Anfragelaenge den
        # Umsetzer frueher aus dem Tritt gebracht hat.
        self.optional = optional

    @property
    def end(self) -> int:
        return self.start + self.count - 1

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Block {self.key} 0x{self.start:04X}-0x{self.end:04X}>"


# Blockgrenzen sind bewusst auf die gueltigen Bereiche gelegt. Eine
# Anfrage, die auch nur ein Register ueber das Ende hinausreicht,
# scheitert komplett - deshalb endet slow_c bei 0x0025 und status_b
# bei 0x100A.
BLOCKS: Final[tuple[Block, ...]] = (
    # 0x0001-0x0010: PV-Eingaenge, Netzleistung, Temperatur, Batterie.
    # In zwei Bloecken statt in 16 Einzelanfragen - damit stammen alle
    # regelungsrelevanten Werte aus demselben Augenblick.
    Block("fast_a", 0x0001, 8, TIER_FAST),
    Block("fast_b", 0x0009, 8, TIER_FAST),
    # 0x0011-0x0025: Fehlercode, Energiezaehler, Zellspannungen,
    # Versionen, Geraetetyp.
    Block("slow_a", 0x0011, 8, TIER_SLOW),
    Block("slow_b", 0x0019, 8, TIER_SLOW),
    Block("slow_c", 0x0021, 5, TIER_SLOW),
    # 0x1000-0x100A: Statusflags.
    Block("status_a", 0x1000, 8, TIER_STATUS),
    Block("status_b", 0x1008, 3, TIER_STATUS),
    # ASCII-Bloecke, statisch. Stuendlich reicht.
    Block("static_mac", 0x1100, 6, TIER_STATIC, optional=True),
    Block("static_comm", 0x1200, 6, TIER_STATIC, optional=True),
)

BLOCKS_BY_KEY: Final = {b.key: b for b in BLOCKS}


def block_for_address(address: int) -> str | None:
    """Liefert den Blockschluessel, in dem eine Adresse gelesen wird."""
    for block in BLOCKS:
        if block.start <= address <= block.end:
            return block.key
    return None


# --- Einzelne Adressen, benannt ---------------------------------------
ADDR_PV_VOLTAGE: Final = (0x0001, 0x0004, 0x0007, 0x000A)
ADDR_PV_CURRENT: Final = (0x0002, 0x0005, 0x0008, 0x000B)
ADDR_PV_POWER: Final = (0x0003, 0x0006, 0x0009, 0x000C)
ADDR_GRID_POWER: Final = 0x000D
ADDR_TEMPERATURE: Final = 0x000E
ADDR_BATTERY_VOLTAGE: Final = 0x000F
ADDR_BATTERY_SOC: Final = 0x0010
ADDR_ERROR_CODE: Final = 0x0011
ADDR_UNKNOWN_0012: Final = 0x0012
ADDR_DAILY_GENERATION: Final = 0x0013
ADDR_MONTHLY_GENERATION: Final = 0x0015
ADDR_DAILY_GRID: Final = 0x0017
ADDR_MONTHLY_GRID: Final = 0x0019
ADDR_DEVICE_ID: Final = 0x001B
ADDR_VERSION_EMS: Final = 0x001C
ADDR_VERSION_INV: Final = 0x001D
ADDR_VERSION_MPPT: Final = 0x001E
ADDR_VERSION_BMS: Final = 0x001F
ADDR_CELL_VOLTAGE_MAX: Final = 0x0020
ADDR_CELL_VOLTAGE_MIN: Final = 0x0021
ADDR_VERSION_SCREEN: Final = 0x0022
ADDR_UNKNOWN_0023: Final = 0x0023
ADDR_UNKNOWN_0024: Final = 0x0024
ADDR_DEVICE_TYPE: Final = 0x0025
ADDR_STATUS_PV: Final = (0x1004, 0x1005, 0x1006, 0x1007)
ADDR_STATUS_INVERTER: Final = 0x1008
ADDR_MAC: Final = 0x1100
ADDR_COMM_FIRMWARE: Final = 0x1200

# 0x002A antwortet mit dem Wert 1, Zweck unbekannt. Bewusst NICHT
# gelesen: die Adresse liegt allein zwischen toten Nachbarn, eine
# eigene Anfrage dafuer waere reine Buslast ohne Erkenntnis.

# Register, die es NICHT gibt - damit niemand sie nochmal sucht:
#   * kein Register fuer die DC-Batterieleistung. 0x000E wurde dafuer
#     getestet und ist es nicht (stand konstant auf 300, waehrend PV
#     zwischen 472 und 493 W lief). Der Wert wird berechnet.
#   * kein Register fuer die Entladetiefe / SoC-Grenze. Die laeuft
#     ausschliesslich ueber hm2mqtt.
#   * keine Einzelspannungen der 16 Zellen, nur Maximum und Minimum.
#   * 0x4000-0x43FF ist write-only und liefert lesend nichts.

# --- Plausibilitaetsgrenzen -------------------------------------------
# Rohwerte, also vor der Skalierung. Werte ausserhalb dieser Grenzen
# werden verworfen und der letzte gute Wert bleibt stehen. Zweites Netz
# unter der Transaction-ID-Pruefung des Transports.
VALID_RANGES: Final[dict[int, tuple[int, int]]] = {
    **{a: (0, 1000) for a in ADDR_PV_VOLTAGE},      # 0 - 100,0 V
    **{a: (0, 300) for a in ADDR_PV_CURRENT},       # 0 - 30,0 A
    **{a: (0, 2000) for a in ADDR_PV_POWER},        # W
    ADDR_TEMPERATURE: (50, 700),                    # 5,0 - 70,0 Grad
    ADDR_BATTERY_VOLTAGE: (400, 600),               # 40,0 - 60,0 V
    ADDR_BATTERY_SOC: (0, 100),                     # %
    ADDR_CELL_VOLTAGE_MAX: (2000, 4000),            # 2,000 - 4,000 V
    ADDR_CELL_VOLTAGE_MIN: (2000, 4000),
}
# Netzleistung ist vorzeichenbehaftet und wird getrennt geprueft.
GRID_POWER_LIMIT: Final = 5000

DEVICE_TYPES: Final[dict[int, str]] = {
    0: "Jupiter C 800 W",
    1: "Jupiter C 1000 W",
    2: "Jupiter C 600 W",
    3: "Jupiter E 800 W",
    4: "Jupiter E 1000 W",
    5: "Jupiter E 600 W",
}

# Fehlertabelle aus dem Benutzerhandbuch, Abschnitt 5.1. Dort sind die
# Codes hexadezimal notiert; das Register 0x0011 liefert denselben Code
# als Dezimalzahl (1062 = 0x426). Deshalb wird vor dem Nachschlagen
# gewandelt.
ERROR_CODES: Final[dict[str, str]] = {
    "404": "Netzseitiger Überhitzungsschutz",
    "406": "Netz-Überspannung",
    "408": "Netz-Unterspannung",
    "409": "Netz-Überfrequenz",
    "410": "Netz-Unterfrequenz",
    "414": "Netz-Inselerkennung",
    "415": "Netz-Überspannung",
    "418": "Gerätefehler",
    "419": "Gerätefehler",
    "422": "Netz-Überstrom",
    # 426 steht nicht im Handbuch - zwischen 422 und 440 ist nichts
    # vergeben. Im Photovoltaikforum laeuft der Thread dazu unter
    # "Fehlercode 426, der Unbekannte". Bewusst als undokumentiert
    # gefuehrt statt geraten.
    "426": "undokumentiert (tritt in der Praxis sporadisch auf)",
    "440": "Batterie-Überspannung",
    "441": "Batterie-Überstrom",
    "442": "Batterie-Unterspannung",
    "443": "Stromumkehr",
    "444": "Startspannung zu niedrig",
    "445": "PV-Überhitzungsschutz",
    "446": "PV1-Überstrom",
    "447": "PV2-Überstrom",
    "448": "PV3-Überstrom",
    "449": "PV4-Überstrom",
    "450": "PV-Minuspol falsch verdrahtet",
    "451": "PE-Erdungsanomalie",
    "452": "PE-Erdungsanomalie",
    "453": "Batterie-Überspannung",
    "454": "Stromumkehr",
    "4C0": "Slave-Kommunikationsfehler",
    "4C1": "Slave-Kommunikationsfehler",
    "4C2": "Temperaturgrenze erreicht",
    "4C3": "Temperaturgrenze erreicht",
    "4C4": "Temperaturgrenze erreicht",
    "530": "Batterieladung zu gering",
    "547": "Batterieladung zu gering",
    "548": "Batterieladung zu gering",
    "5C0": "CT-Verbindungsfehler",
    "5C1": "Phasenfolge-Erkennung fehlgeschlagen",
    "5C2": "WLAN-Signalanomalie",
    "5C3": "Bluetooth-Status auffällig",
    "5C4": "OTA-Update fehlgeschlagen",
    "5C5": "OTA-Update fehlgeschlagen",
    "5C6": "OTA-Update fehlgeschlagen",
    "5C7": "Netzwerkanomalie",
    "5C8": "Netzwerkanomalie",
    "5C9": "Netzwerkanomalie",
    "5CA": "Netzwerkanomalie",
    "5CB": "Netzwerkanomalie",
}


def error_text(code: int) -> str:
    """Fehlercode in Klartext. 0 heisst: kein Fehler."""
    if not code:
        return "kein Fehler"
    hex_code = f"{code:X}"
    return f"0x{hex_code} - {ERROR_CODES.get(hex_code, 'nicht im Handbuch')}"


SERVICE_REGISTER_DUMP: Final = "register_dump"
SERVICE_READ_REGISTER: Final = "read_register"
EVENT_REGISTER_DUMP: Final = f"{DOMAIN}_register_dump"
