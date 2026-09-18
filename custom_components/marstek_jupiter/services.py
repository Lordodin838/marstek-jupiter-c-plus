"""Dienste: Registerabzug und Einzelabfrage.

Beides laeuft ueber denselben Client wie die laufende Abfrage. Damit ist
das alte Problem erledigt, dass ein externes Scan-Skript und Home
Assistant gleichzeitig auf den Umsetzer zugreifen und sich gegenseitig
die Antworten vertauschen: es gibt nur noch eine Verbindung und ein Lock.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    EVENT_REGISTER_DUMP,
    SERVICE_READ_REGISTER,
    SERVICE_REGISTER_DUMP,
)
from .modbus import (
    MAX_REGISTERS,
    ModbusError,
    ModbusExceptionResponse,
    to_ascii,
    to_int16,
    to_int32,
    to_uint32,
)

_LOGGER = logging.getLogger(__name__)

# Gruendlich durchsuchte Bereiche. Hier wird bei Fehlschlag halbiert,
# deshalb werden auch isolierte Einzelregister gefunden - etwa 0x002A,
# das jede Stichprobensuche uebersieht.
SCAN_RANGES: tuple[tuple[int, int, str], ...] = (
    (0x0000, 0x03FF, "Datenblock"),
    (0x1000, 0x13FF, "Statusflags"),
    (0x4000, 0x43FF, "Schreibregister (lesend meist leer)"),
)
COARSE_STEP = 0x0100
COARSE_PROBES = (0x00, 0x80)
PASSES = 3

SCHEMA_DUMP = vol.Schema(
    {
        vol.Optional("label", default="abzug"): cv.string,
        vol.Optional("sweep", default=False): cv.boolean,
    }
)

SCHEMA_READ = vol.Schema(
    {
        vol.Required("address"): vol.All(vol.Coerce(int), vol.Range(0, 0xFFFF)),
        vol.Optional("count", default=1): vol.All(
            vol.Coerce(int), vol.Range(1, MAX_REGISTERS)
        ),
        vol.Optional("data_type", default="uint16"): vol.In(
            ["uint16", "int16", "uint32", "int32", "string", "raw"]
        ),
    }
)


def _only_client(hass: HomeAssistant):
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if getattr(entry, "runtime_data", None) is not None
    ]
    if not entries:
        raise HomeAssistantError("Keine eingerichtete Jupiter-Integration gefunden")
    return entries[0].runtime_data.coordinator.client


def async_setup_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_REGISTER_DUMP):
        return

    async def _handle_read(call: ServiceCall) -> ServiceResponse:
        client = _only_client(hass)
        address = call.data["address"]
        count = call.data["count"]
        data_type = call.data["data_type"]
        try:
            registers = await client.read_holding(address, count)
        except ModbusExceptionResponse as err:
            return {
                "address": f"0x{address:04X}",
                "error": f"Modbus-Exception {err.code}",
                "hint": "Exception 2 heisst: diese Adresse gibt es nicht.",
            }
        except ModbusError as err:
            raise HomeAssistantError(str(err)) from err

        return {
            "address": f"0x{address:04X}",
            "registers": registers,
            "value": _decode(registers, data_type),
        }

    async def _handle_dump(call: ServiceCall) -> ServiceResponse:
        client = _only_client(hass)
        label = call.data["label"]
        sweep = call.data["sweep"]

        _LOGGER.info("Registerabzug gestartet (label=%s, sweep=%s)", label, sweep)
        result = await _scan(client, sweep)
        path = await hass.async_add_executor_job(
            _write_report, hass.config.path("marstek_jupiter"), result, label, sweep
        )
        hass.bus.async_fire(
            EVENT_REGISTER_DUMP,
            {"label": label, "path": path, "registers": len(result["register"])},
        )
        _LOGGER.info("Registerabzug geschrieben: %s", path)
        return {"path": path, "summary": result["summary"]}

    hass.services.async_register(
        DOMAIN,
        SERVICE_READ_REGISTER,
        _handle_read,
        schema=SCHEMA_READ,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REGISTER_DUMP,
        _handle_dump,
        schema=SCHEMA_DUMP,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _decode(registers: list[int], data_type: str) -> Any:
    if data_type == "raw":
        return registers
    if data_type == "string":
        return to_ascii(registers)
    if data_type == "int16":
        return [to_int16(r) for r in registers]
    if data_type == "uint32":
        return [
            to_uint32(registers[i], registers[i + 1])
            for i in range(0, len(registers) - 1, 2)
        ]
    if data_type == "int32":
        return [
            to_int32(registers[i], registers[i + 1])
            for i in range(0, len(registers) - 1, 2)
        ]
    return registers


async def _probe(client, address: int, count: int) -> list[int] | None:
    try:
        return await client.read_holding(address, count)
    except ModbusError:
        return None


async def _discover(client, start: int, end: int) -> list[int]:
    """Sucht die tatsaechlichen Grenzen gueltiger Bereiche.

    Eine Anfrage, die auch nur teilweise ins Leere reicht, scheitert
    komplett. Deshalb bei Fehlschlag halbieren, bis auf Einzelregister
    hinunter - ein starres 8er-Raster verliert sonst die Register an den
    Raendern.
    """
    valid: list[int] = []
    todo: list[tuple[int, int]] = []
    address = start
    while address <= end:
        todo.append((address, min(MAX_REGISTERS, end - address + 1)))
        address += MAX_REGISTERS

    while todo:
        addr, count = todo.pop(0)
        if await _probe(client, addr, count) is not None:
            valid.extend(range(addr, addr + count))
            continue
        if count == 1:
            continue
        # Abkuerzung fuer grosse leere Zonen: antworten weder erstes noch
        # letztes Register des Blocks, gilt der ganze Block als leer.
        if count == MAX_REGISTERS:
            first = await _probe(client, addr, 1)
            last = await _probe(client, addr + count - 1, 1)
            if first is None and last is None:
                continue
            if first is not None:
                valid.append(addr)
            if last is not None:
                valid.append(addr + count - 1)
            if count > 2:
                todo.insert(0, (addr + 1, count - 2))
            continue
        half = count // 2
        todo.insert(0, (addr + half, count - half))
        todo.insert(0, (addr, half))

    return sorted(set(valid))


async def _coarse_sweep(client) -> list[int]:
    """Grobsuche ueber den 16-Bit-Adressraum.

    Zwei Stichproben je 256er-Seite. EHRLICHE GRENZE: findet Bloecke,
    keine Einzelgaenger. Ein gueltiges Register zwischen toten Nachbarn
    laesst jede 8er-Stichprobe scheitern und bleibt unsichtbar.
    """
    covered = {
        page
        for start, end, _ in SCAN_RANGES
        for page in range(start & ~0xFF, end + 1, COARSE_STEP)
    }
    hits: list[int] = []
    for page in range(0x0000, 0x10000, COARSE_STEP):
        if page in covered:
            continue
        for offset in COARSE_PROBES:
            addr = page + offset
            if addr + MAX_REGISTERS - 1 > 0xFFFF:
                continue
            if await _probe(client, addr, MAX_REGISTERS) is not None:
                hits.append(page)
                break
    return hits


def _runs(addresses: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for addr in addresses:
        if out and addr == out[-1][-1] + 1 and len(out[-1]) < MAX_REGISTERS:
            out[-1].append(addr)
        else:
            out.append([addr])
    return out


def _majority(values: list[int | None]) -> tuple[int | None, bool]:
    real = [v for v in values if v is not None]
    if not real:
        return None, False
    best, hits = None, 0
    for value in set(real):
        count = real.count(value)
        if count > hits:
            best, hits = value, count
    return best, hits >= 2


async def _scan(client, sweep: bool) -> dict[str, Any]:
    ranges = list(SCAN_RANGES)
    sweep_hits: list[int] = []
    if sweep:
        sweep_hits = await _coarse_sweep(client)
        ranges.extend(
            (page, page + COARSE_STEP - 1, f"Grobsuche 0x{page:04X}")
            for page in sweep_hits
        )

    blocks: list[tuple[list[int], str]] = []
    area: dict[int, str] = {}
    for start, end, label in ranges:
        valid = await _discover(client, start, end)
        for chunk in _runs(valid):
            blocks.append((chunk, label))
            for addr in chunk:
                area[addr] = label

    samples: dict[int, list[int | None]] = {}
    for _ in range(PASSES):
        for chunk, _label in blocks:
            values = await _probe(client, chunk[0], len(chunk))
            for index, addr in enumerate(chunk):
                samples.setdefault(addr, []).append(
                    values[index] if values else None
                )

    register: dict[str, Any] = {}
    certain = 0
    for addr in sorted(samples):
        value, sure = _majority(samples[addr])
        certain += bool(sure)
        register[f"0x{addr:04X}"] = {
            "adresse": f"0x{addr:04X}",
            "bereich": area.get(addr, "?"),
            "wert": value,
            "sicher": bool(sure),
            "messungen": samples[addr],
        }

    return {
        "register": register,
        "grobsuche": sweep,
        "grobsuche_treffer": [f"0x{p:04X}" for p in sweep_hits],
        "summary": {
            "belegt": len(register),
            "eindeutig": certain,
            "unsicher": len(register) - certain,
        },
    }


def _write_report(
    directory: str, result: dict[str, Any], label: str, sweep: bool
) -> str:
    os.makedirs(directory, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    base = os.path.join(directory, f"regdump_{label}_{stamp}")

    payload = {
        "erzeugt": datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "grobsuche": sweep,
        "grobsuche_treffer": result["grobsuche_treffer"],
        "zusammenfassung": result["summary"],
        "register": result["register"],
    }
    with open(f"{base}.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, ensure_ascii=False)

    lines = [
        "Registerabzug Marstek Jupiter C+",
        f"erzeugt: {payload['erzeugt']}",
        f"label:   {label}",
        "",
    ]
    if sweep:
        hits = result["grobsuche_treffer"]
        lines.append(
            "Grobsuche ueber 0x0000-0xFFFF: "
            + (f"Treffer auf {', '.join(hits)}" if hits else "keine weiteren Seiten")
        )
        lines.append("(Findet Bloecke, keine isolierten Einzelregister.)")
        lines.append("")
    lines += [
        "Adresse  Wert    sicher  Bereich",
        "-" * 56,
    ]
    for key in sorted(result["register"], key=lambda k: int(k, 16)):
        entry = result["register"][key]
        lines.append(
            "%-8s %-7s %-7s %s"
            % (
                key,
                entry["wert"],
                "ja" if entry["sicher"] else "NEIN",
                entry["bereich"],
            )
        )
    with open(f"{base}.txt", "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    return f"{base}.json"
