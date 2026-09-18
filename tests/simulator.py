"""Simulierter Jupiter C+ mit den Eigenheiten des echten Geraets.

Nachgebildet werden:
  * hoechstens 8 Register pro Anfrage, darueber Exception 3
  * nur Funktionscode 3, alles andere Exception 1
  * eine Anfrage, die auch nur teilweise ueber das Ende eines gueltigen
    Bereichs hinausreicht, scheitert KOMPLETT (Exception 2)
  * auf Wunsch: verirrte Antworten mit fremder Transaction-ID und
    verzoegerte Antworten, die nach dem Timeout eintreffen

Die Registerwerte sind echte Messwerte der Anlage vom 18.09.2026.
"""

from __future__ import annotations

import asyncio
import struct

# Gueltige Bereiche des echten Geraets.
REGISTERS: dict[int, int] = {
    # PV-Eingaenge
    0x0001: 363, 0x0002: 0, 0x0003: 0,
    0x0004: 383, 0x0005: 1, 0x0006: 3,
    0x0007: 235, 0x0008: 0, 0x0009: 0,
    0x000A: 224, 0x000B: 0, 0x000C: 0,
    # Netz, Temperatur, Batterie
    0x000D: 162, 0x000E: 280, 0x000F: 530, 0x0010: 90,
    # Fehlercode und Nachbar
    0x0011: 0, 0x0012: 0,
    # Energiezaehler, uint32 hohes Wort zuerst
    0x0013: 0, 0x0014: 575,
    0x0015: 0, 0x0016: 3167,
    0x0017: 0, 0x0018: 394,
    0x0019: 0, 0x001A: 2946,
    # Versionen
    0x001B: 11, 0x001C: 142, 0x001D: 110, 0x001E: 213, 0x001F: 37,
    # Zellspannungen
    0x0020: 3317, 0x0021: 3315,
    0x0022: 111, 0x0023: 38, 0x0024: 0, 0x0025: 0,
    # Einzelgaenger zwischen toten Nachbarn
    0x002A: 1,
    # Statusflags
    0x1000: 1, 0x1001: 0, 0x1002: 0, 0x1003: 0,
    0x1004: 0, 0x1005: 1, 0x1006: 0, 0x1007: 0,
    0x1008: 1, 0x1009: 0, 0x100A: 0,
}

# MAC 24:21:5E:E5:67:4D und Modul-Firmware 202512040647, je zwei
# ASCII-Zeichen pro Register.
for offset, pair in enumerate(["24", "21", "5e", "e5", "67", "4d"]):
    REGISTERS[0x1100 + offset] = struct.unpack(">H", pair.encode())[0]
for offset, pair in enumerate(["20", "25", "12", "04", "06", "47"]):
    REGISTERS[0x1200 + offset] = struct.unpack(">H", pair.encode())[0]


class JupiterSimulator:
    """Modbus-TCP-Server, der sich wie der Jupiter verhaelt."""

    def __init__(
        self,
        unit: int = 1,
        stray_before: int = 0,
        delay_first: float = 0.0,
    ) -> None:
        self.unit = unit
        # Anzahl verirrter Antworten, die vor der richtigen gesendet werden
        self.stray_before = stray_before
        # Verzoegerung der ersten Antwort - bildet den Fall nach, in dem
        # Home Assistant zu frueh aufgibt und die Antwort danach eintrifft
        self.delay_first = delay_first
        self.requests = 0
        self._server: asyncio.AbstractServer | None = None
        self.port = 0

    async def start(self) -> int:
        self._server = await asyncio.start_server(
            self._handle, "127.0.0.1", 0
        )
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                header = await reader.readexactly(6)
                tid, pid, length = struct.unpack(">HHH", header)
                body = await reader.readexactly(length)
                unit, function = body[0], body[1]
                self.requests += 1

                if self.stray_before:
                    self.stray_before -= 1
                    # Fremde Antwort mit falscher Transaction-ID, so wie
                    # der Umsetzer sie durchreicht.
                    stray = struct.pack(
                        ">HHHBBB", (tid + 7) % 65535, 0, 5, unit, 3, 2
                    ) + struct.pack(">H", 0xDEAD)
                    writer.write(stray)
                    await writer.drain()

                if self.delay_first:
                    delay, self.delay_first = self.delay_first, 0.0
                    await asyncio.sleep(delay)

                writer.write(self._respond(tid, unit, function, body))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    def _respond(self, tid: int, unit: int, function: int, body: bytes) -> bytes:
        def exception(code: int) -> bytes:
            return struct.pack(">HHHBBB", tid, 0, 3, unit, function | 0x80, code)

        if unit != self.unit:
            return exception(0x0B)
        if function != 3:
            # Input-Register (FC4) kennt das Geraet nicht.
            return exception(1)

        address, count = struct.unpack(">HH", body[2:6])
        if count < 1 or count > 8:
            return exception(3)
        # Eine Anfrage, die auch nur teilweise ins Leere reicht,
        # scheitert komplett.
        if any(a not in REGISTERS for a in range(address, address + count)):
            return exception(2)

        payload = b"".join(
            struct.pack(">H", REGISTERS[a])
            for a in range(address, address + count)
        )
        return (
            struct.pack(">HHHBBB", tid, 0, 3 + len(payload), unit, 3, len(payload))
            + payload
        )
