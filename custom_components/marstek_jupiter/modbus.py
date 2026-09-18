"""Modbus-TCP-Transport fuer den Marstek Jupiter C+ hinter einem Elfin-Umsetzer.

Warum kein pymodbus
-------------------
Der RS485-WLAN-Umsetzer (Elfin EW11/EE11) hat zwei Eigenheiten, die eine
gewoehnliche Modbus-Bibliothek nicht sauber behandelt:

1. Er bearbeitet immer nur EINE Anfrage. Kommen zwei kurz hintereinander,
   ordnet er Antworten der falschen Anfrage zu. Sichtbar wird das als
   "richtiger Wert im falschen Sensor" - ein Ladezustand von 3308 %, weil
   die Antwort der Zellspannungs-Abfrage im SoC-Sensor landete.

2. Er reicht fremde Antworten mit passender Transaction-ID durch.

Deshalb dieser kleine Transport: ein einziger Socket, ein Lock, strenge
Pruefung von Transaction-ID, Protokoll-ID, Unit-ID und Antwortlaenge. Was
nicht exakt zur eigenen Anfrage passt, wird verworfen statt uebernommen.

Geraetegrenzen, alle am realen Geraet nachgemessen:
  * hoechstens 8 Register pro Anfrage, darueber Exception 3
  * nur Holding-Register (FC3), Input-Register (FC4) gibt Exception 1
  * eine Anfrage, die auch nur teilweise ueber das Ende eines gueltigen
    Bereichs hinausreicht, scheitert KOMPLETT
"""

from __future__ import annotations

import asyncio
import logging
import struct

_LOGGER = logging.getLogger(__name__)

MAX_REGISTERS = 8
"""Geraetelimit. Nicht erhoehen - darueber antwortet der Jupiter mit
Exception 3 (illegal data value)."""


class ModbusError(Exception):
    """Basisfehler dieses Transports."""


class ModbusConnectionError(ModbusError):
    """Verbindung steht nicht oder ist abgerissen."""


class ModbusResponseError(ModbusError):
    """Antwort kam an, passt aber nicht zur Anfrage."""


class ModbusExceptionResponse(ModbusError):
    """Das Geraet hat die Anfrage aktiv abgelehnt.

    Das ist eine Auskunft, kein Stoerfall: Exception 2 heisst schlicht
    "diese Adresse gibt es nicht". Wird deshalb nicht wiederholt.
    """

    def __init__(self, code: int) -> None:
        self.code = code
        super().__init__(f"Modbus-Exception {code}")


class JupiterModbusClient:
    """Serialisierter Modbus-TCP-Client mit strenger Antwortpruefung."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_id: int = 1,
        timeout: float = 5.0,
        message_wait: float = 0.15,
        retries: int = 2,
    ) -> None:
        self._host = host
        self._port = port
        self._unit = unit_id
        self._timeout = timeout
        self._message_wait = message_wait
        self._retries = retries

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._tid = 0
        # Serialisiert ALLE Zugriffe. Der Umsetzer vertraegt keine zwei
        # offenen Anfragen - das ist die zentrale Schutzmassnahme.
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        return self._host

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        await self.close()
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=self._timeout,
            )
        except (OSError, asyncio.TimeoutError) as err:
            self._reader = self._writer = None
            raise ModbusConnectionError(
                f"Verbindung zu {self._host}:{self._port} nicht moeglich: {err}"
            ) from err

    async def close(self) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        if writer is None:
            return
        try:
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), timeout=2)
        except (OSError, asyncio.TimeoutError):
            pass

    async def read_holding(self, address: int, count: int) -> list[int]:
        """Liest ``count`` Holding-Register ab ``address``.

        Wiederholt bei Verbindungs- und Zeitfehlern, NICHT bei einer
        Exception des Geraets - die ist eine gueltige Antwort.
        """
        if not 1 <= count <= MAX_REGISTERS:
            raise ValueError(
                f"{count} Register angefragt, erlaubt sind 1 bis {MAX_REGISTERS}"
            )

        async with self._lock:
            last_err: Exception | None = None
            for attempt in range(self._retries + 1):
                if not self.connected:
                    try:
                        await self.connect()
                    except ModbusConnectionError as err:
                        last_err = err
                        await asyncio.sleep(self._message_wait)
                        continue
                try:
                    result = await self._transact(address, count)
                except ModbusExceptionResponse:
                    await asyncio.sleep(self._message_wait)
                    raise
                except (ModbusConnectionError, ModbusResponseError) as err:
                    last_err = err
                    _LOGGER.debug(
                        "Lesefehler 0x%04X+%d (Versuch %d/%d): %s",
                        address, count, attempt + 1, self._retries + 1, err,
                    )
                    # Nach einer verirrten oder abgebrochenen Antwort ist
                    # der Datenstrom nicht mehr vertrauenswuerdig - neu
                    # aufbauen statt weiterlesen.
                    await self.close()
                    await asyncio.sleep(self._message_wait)
                    continue
                await asyncio.sleep(self._message_wait)
                return result

            raise last_err or ModbusConnectionError("Lesen fehlgeschlagen")

    async def _transact(self, address: int, count: int) -> list[int]:
        assert self._reader is not None and self._writer is not None

        self._tid = (self._tid % 65530) + 1
        tid = self._tid
        request = struct.pack(
            ">HHHBBHH", tid, 0, 6, self._unit, 3, address, count
        )

        try:
            self._writer.write(request)
            await self._writer.drain()
        except OSError as err:
            raise ModbusConnectionError(f"Senden fehlgeschlagen: {err}") from err

        # Bis zu vier fremde Antworten verwerfen. Genau hier entsteht sonst
        # der Fehler "richtiger Wert im falschen Sensor".
        for _ in range(4):
            header = await self._read_exactly(6)
            rtid, pid, length = struct.unpack(">HHH", header)

            if length < 2 or length > 260:
                raise ModbusResponseError(f"unplausible Laenge {length}")

            body = await self._read_exactly(length)

            if rtid != tid or pid != 0 or body[0] != self._unit:
                _LOGGER.debug(
                    "fremde Antwort verworfen (TID %d statt %d)", rtid, tid
                )
                continue

            function = body[1]
            if function == 0x83:
                raise ModbusExceptionResponse(body[2])
            if function != 3:
                raise ModbusResponseError(f"Funktionscode {function}")

            nbytes = body[2]
            payload = body[3 : 3 + nbytes]
            if nbytes != count * 2 or len(payload) != nbytes:
                raise ModbusResponseError(
                    f"Laenge passt nicht ({nbytes} statt {count * 2})"
                )

            return list(struct.unpack(f">{count}H", payload))

        raise ModbusResponseError("nur fremde Antworten erhalten")

    async def _read_exactly(self, count: int) -> bytes:
        assert self._reader is not None
        try:
            return await asyncio.wait_for(
                self._reader.readexactly(count), timeout=self._timeout
            )
        except asyncio.IncompleteReadError as err:
            raise ModbusConnectionError("Verbindung abgebrochen") from err
        except asyncio.TimeoutError as err:
            raise ModbusConnectionError("Zeitueberschreitung") from err
        except OSError as err:
            raise ModbusConnectionError(f"Lesefehler: {err}") from err


# --- Wertwandlung -----------------------------------------------------
# Wortreihenfolge big-endian (hohes Wort zuerst), so wie die
# Modbus-Integration von Home Assistant uint32 standardmaessig liest.


def to_int16(raw: int) -> int:
    return raw - 0x10000 if raw > 0x7FFF else raw


def to_uint32(high: int, low: int) -> int:
    return (high << 16) | low


def to_int32(high: int, low: int) -> int:
    value = (high << 16) | low
    return value - 0x1_0000_0000 if value > 0x7FFF_FFFF else value


def to_ascii(registers: list[int]) -> str:
    """Zwei ASCII-Zeichen je Register, wie bei MAC und Modul-Firmware."""
    raw = b"".join(struct.pack(">H", r) for r in registers)
    return raw.decode("ascii", errors="ignore").strip("\x00").strip()
