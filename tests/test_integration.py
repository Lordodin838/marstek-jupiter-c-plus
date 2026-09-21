#!/usr/bin/env python3
"""Pruefung der Integration ohne Home Assistant.

Laeuft gegen den Simulator in simulator.py und gegen Attrappen der
Home-Assistant-Schnittstellen. Aufruf:  python3 tests/test_integration.py
"""

from __future__ import annotations

import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from simulator import REGISTERS, JupiterSimulator  # noqa: E402

from custom_components.marstek_jupiter import binary_sensor as bs  # noqa: E402
from custom_components.marstek_jupiter import const  # noqa: E402
from custom_components.marstek_jupiter import sensor as sn  # noqa: E402
from custom_components.marstek_jupiter.coordinator import JupiterData  # noqa: E402
from custom_components.marstek_jupiter.modbus import (  # noqa: E402
    JupiterModbusClient,
    ModbusExceptionResponse,
    to_ascii,
    to_int16,
    to_uint32,
)

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
    else:
        FAILED.append(f"{name}: {detail}")


def equal(name: str, got, want) -> None:
    check(name, got == want, f"erhalten {got!r}, erwartet {want!r}")


# --- 1. Registerkarte in sich stimmig --------------------------------
def test_register_map() -> None:
    for block in const.BLOCKS:
        check(
            f"Block {block.key} hoechstens 8 Register",
            block.count <= 8,
            f"{block.count} Register",
        )
        missing = [
            a for a in range(block.start, block.end + 1) if a not in REGISTERS
        ]
        check(
            f"Block {block.key} liegt vollstaendig im gueltigen Bereich",
            not missing,
            f"nicht vorhanden: {[hex(a) for a in missing]}",
        )

    # Jede Adresse, die eine Entitaet braucht, muss in einem Block liegen -
    # sonst bliebe der Sensor fuer immer leer.
    for description in sn.SENSORS:
        for address in description.addresses:
            check(
                f"Adresse 0x{address:04X} von {description.key} wird gelesen",
                const.block_for_address(address) is not None,
                "in keinem Leseblock",
            )
    for description in bs.BINARY_SENSORS:
        check(
            f"Adresse 0x{description.address:04X} von {description.key} wird gelesen",
            const.block_for_address(description.address) is not None,
            "in keinem Leseblock",
        )

    keys = [d.key for d in sn.SENSORS] + [d.key for d in bs.BINARY_SENSORS]
    equal("Entitaets-Schluessel eindeutig", len(keys), len(set(keys)))

    legacy = [
        d.legacy_unique_id
        for d in (*sn.SENSORS, *bs.BINARY_SENSORS)
        if d.legacy_unique_id
    ]
    equal("uebernommene unique_ids eindeutig", len(legacy), len(set(legacy)))


# --- 2. Wertwandlung --------------------------------------------------
def test_decoding() -> None:
    equal("int16 positiv", to_int16(162), 162)
    equal("int16 negativ", to_int16(65374), -162)
    equal("uint32", to_uint32(0, 575), 575)
    # Reale MAC der Anlage: 24:21:5E:E5:67:4D
    mac_registers = [REGISTERS[0x1100 + i] for i in range(6)]
    equal("MAC aus ASCII-Registern", to_ascii(mac_registers), "24215ee5674d")
    firmware = [REGISTERS[0x1200 + i] for i in range(6)]
    equal("Modul-Firmware", to_ascii(firmware), "202512040647")

    # 1062 dezimal = 0x426 - genau der Fall vom 15.09.2026
    check(
        "Fehlercode 1062 wird als 0x426 gedeutet",
        const.error_text(1062).startswith("0x426 -"),
        const.error_text(1062),
    )
    equal("Fehlercode 0", const.error_text(0), "kein Fehler")
    check(
        "bekannter Code aus dem Handbuch",
        "Netz-Überspannung" in const.error_text(0x406),
        const.error_text(0x406),
    )


# --- 3. Sensorwerte gegen die echten Messwerte ------------------------
def test_sensor_values() -> None:
    data = JupiterData(registers=dict(REGISTERS))
    values = {d.key: d.value_fn(data) for d in sn.SENSORS}

    equal("PV1 Spannung", values["pv1_voltage"], 36.3)
    equal("PV2 Leistung", values["pv2_power"], 3)
    equal("PV Gesamtleistung", values["pv_total_power"], 3)
    equal("Netzleistung", values["grid_power"], 162)
    equal("Batteriespannung", values["battery_voltage"], 53.0)
    equal("Ladezustand", values["battery_soc"], 90)
    equal("Tagesertrag", values["daily_generation"], 5.75)
    equal("Monatsertrag", values["monthly_generation"], 31.67)
    equal("Tageseinspeisung", values["daily_grid"], 3.94)
    equal("Monatseinspeisung", values["monthly_grid"], 29.46)
    equal("Zellspannung max", values["cell_voltage_max"], 3.317)
    equal("Zelldrift in mV", values["cell_voltage_delta"], 2)
    equal("Temperatur", values["temperature"], 28.0)
    equal("Geraetetyp", values["device_type_text"], "Jupiter C 800 W")
    equal("EMS-Version", values["ems_version"], 142)
    equal("MAC-Sensor", values["mac_address"], "24215ee5674d")

    # PV 3 W, Netz 162 W Abgabe -> 159 W aus der Batterie.
    # Deckt sich mit dem Wert, den die bisherige Template-Loesung zeigt.
    equal("Batterieleistung berechnet", values["battery_power"], -159)


# --- 4. Plausibilitaetsfilter ----------------------------------------
def test_sanity_filter() -> None:
    from custom_components.marstek_jupiter.coordinator import JupiterCoordinator

    data = JupiterData()
    store = JupiterCoordinator._store

    # Erst ein gueltiger Ladezustand, dann die Sorte Ausreisser, die am
    # 14.09. im Verlauf stand: 3308 ist eine Zellspannung im SoC-Sensor.
    store(None, data, const.ADDR_BATTERY_SOC, [90])
    rejected = store(None, data, const.ADDR_BATTERY_SOC, [3308])
    equal("unplausibler SoC wird verworfen", rejected, 1)
    equal("letzter guter SoC bleibt stehen", data.registers[0x0010], 90)

    store(None, data, const.ADDR_BATTERY_VOLTAGE, [530])
    store(None, data, const.ADDR_BATTERY_VOLTAGE, [0])
    equal("Batteriespannung 0,0 V wird verworfen", data.registers[0x000F], 530)

    # Netzbezug ist gueltig und muss durchkommen.
    store(None, data, const.ADDR_GRID_POWER, [65374])
    equal("Netzbezug -162 W kommt durch", to_int16(data.registers[0x000D]), -162)


# --- 5. Transport gegen den Simulator ---------------------------------
async def test_transport() -> None:
    sim = JupiterSimulator()
    port = await sim.start()
    client = JupiterModbusClient("127.0.0.1", port, timeout=2, message_wait=0.01)
    try:
        for block in const.BLOCKS:
            values = await client.read_holding(block.start, block.count)
            want = [
                REGISTERS[block.start + i] for i in range(block.count)
            ]
            equal(f"Block {block.key} gelesen", values, want)

        # Ueber das Ende des gueltigen Bereichs hinaus: das Geraet lehnt
        # die GANZE Anfrage ab, auch wenn die erste Haelfte gueltig waere.
        try:
            await client.read_holding(0x0021, 8)
            check("Block ueber 0x0025 hinaus wird abgelehnt", False, "kein Fehler")
        except ModbusExceptionResponse as err:
            equal("Exception 2 bei Bereichsueberschreitung", err.code, 2)

        # Mehr als 8 Register faengt schon der Client ab.
        try:
            await client.read_holding(0x0001, 9)
            check("mehr als 8 Register wird abgefangen", False, "kein Fehler")
        except ValueError:
            check("mehr als 8 Register wird abgefangen", True)
    finally:
        await client.close()
        await sim.stop()


async def test_stray_response() -> None:
    """Der Kernfall: verirrte Antwort mit fremder Transaction-ID.

    Genau hierdurch landete am 14.09. eine Zellspannung im SoC-Sensor.
    Der Transport muss die fremde Antwort verwerfen und trotzdem den
    richtigen Wert liefern.
    """
    sim = JupiterSimulator(stray_before=2)
    port = await sim.start()
    client = JupiterModbusClient("127.0.0.1", port, timeout=2, message_wait=0.01)
    try:
        values = await client.read_holding(0x0009, 8)
        want = [REGISTERS[0x0009 + i] for i in range(8)]
        equal("verirrte Antwort wird verworfen", values, want)
        equal("Ladezustand bleibt korrekt", values[7], 90)
    finally:
        await client.close()
        await sim.stop()


async def test_late_response() -> None:
    """Antwort trifft nach dem Timeout ein.

    Bis zum Timeout-Fix ordnete Home Assistant sie der naechsten Anfrage
    zu. Hier muss der Wert der naechsten Anfrage trotzdem stimmen.
    """
    sim = JupiterSimulator(delay_first=1.0)
    port = await sim.start()
    client = JupiterModbusClient(
        "127.0.0.1", port, timeout=0.3, message_wait=0.01, retries=2
    )
    try:
        values = await client.read_holding(0x0009, 8)
        want = [REGISTERS[0x0009 + i] for i in range(8)]
        equal("nach verspaeteter Antwort stimmen die Werte", values, want)
    finally:
        await client.close()
        await sim.stop()


async def test_serialisation() -> None:
    """Zwanzig gleichzeitige Anfragen duerfen sich nicht ueberholen."""
    sim = JupiterSimulator()
    port = await sim.start()
    client = JupiterModbusClient("127.0.0.1", port, timeout=2, message_wait=0.0)
    try:
        results = await asyncio.gather(
            *[
                client.read_holding(0x0009, 8) if i % 2 else
                client.read_holding(0x0001, 8)
                for i in range(20)
            ]
        )
        ok = all(
            values == [REGISTERS[(0x0009 if i % 2 else 0x0001) + k] for k in range(8)]
            for i, values in enumerate(results)
        )
        check("20 gleichzeitige Anfragen bleiben getrennt", ok, "Werte vertauscht")
    finally:
        await client.close()
        await sim.stop()


def test_request_budget() -> None:
    """Anfragen je Minute - der Grund fuer den Umbau auf Bloecke."""
    per_minute = 0.0
    intervals = {
        const.TIER_FAST: const.DEFAULT_FAST_INTERVAL,
        const.TIER_SLOW: const.DEFAULT_SLOW_INTERVAL,
        const.TIER_STATUS: const.DEFAULT_STATUS_INTERVAL,
        const.TIER_STATIC: const.DEFAULT_STATIC_INTERVAL,
    }
    for block in const.BLOCKS:
        per_minute += 60 / intervals[block.tier]
    check(
        f"Buslast unter 20 Anfragen/Minute (ist {per_minute:.1f})",
        per_minute < 20,
        f"{per_minute:.1f}",
    )
    print(f"    Buslast: {per_minute:.1f} Anfragen/Minute "
          f"(bisherige YAML-Loesung: rund 48)")


def test_coordinator_notifies() -> None:
    """Regression 1.0.0: mit always_update=False blieben alle Entitaeten
    nach dem ersten Wert stehen, weil jede Runde dasselbe Objekt liefert."""
    from custom_components.marstek_jupiter.coordinator import JupiterCoordinator

    coordinator = JupiterCoordinator(
        None, None, config_entry=None, fast_interval=10, slow_interval=60,
        status_interval=300, static_interval=3600, entry_title="Test",
    )
    check("Coordinator benachrichtigt nach jeder Runde (always_update)",
          coordinator.always_update is True, "always_update ist nicht True")


async def main() -> int:
    test_register_map()
    test_decoding()
    test_sensor_values()
    test_sanity_filter()
    test_request_budget()
    test_coordinator_notifies()
    await test_transport()
    await test_stray_response()
    await test_late_response()
    await test_serialisation()

    print(f"\n{len(PASSED)} Pruefungen bestanden.")
    if FAILED:
        print(f"{len(FAILED)} FEHLGESCHLAGEN:")
        for item in FAILED:
            print("  -", item)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
