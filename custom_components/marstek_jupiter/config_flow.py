"""Einrichtung ueber die Oberflaeche."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    ADDR_DEVICE_TYPE,
    ADDR_MAC,
    CONF_ADOPT_LEGACY,
    CONF_ERROR_FALLBACK,
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
    DEFAULT_STATUS_INTERVAL,
    DEFAULT_TIMEOUT,
    DEFAULT_UNIT_ID,
    DEVICE_TYPES,
    DOMAIN,
)
from .modbus import JupiterModbusClient, ModbusError, to_ascii

_LOGGER = logging.getLogger(__name__)

STEP_USER = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(1, 65535)
        ),
        vol.Optional(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): vol.All(
            vol.Coerce(int), vol.Range(0, 247)
        ),
        vol.Optional(CONF_ADOPT_LEGACY, default=True): bool,
    }
)


async def _probe(host: str, port: int, unit_id: int) -> dict[str, Any]:
    """Verbindung pruefen und Geraet identifizieren."""
    client = JupiterModbusClient(host=host, port=port, unit_id=unit_id)
    try:
        await client.connect()
        # 0x0021-0x0025 endet genau am letzten gueltigen Register. Ein
        # Block darueber hinaus wuerde komplett scheitern.
        tail = await client.read_holding(0x0021, 5)
        device_type = tail[ADDR_DEVICE_TYPE - 0x0021]
        mac = None
        try:
            mac_registers = await client.read_holding(ADDR_MAC, 6)
            text = to_ascii(mac_registers)
            if len(text) == 12:
                mac = ":".join(text[i : i + 2] for i in range(0, 12, 2)).lower()
        except ModbusError:
            # Aeltere Firmware kennt den MAC-Block nicht. Kein Grund,
            # die Einrichtung abzubrechen.
            _LOGGER.debug("MAC-Block 0x1100 nicht lesbar")
        return {"device_type": device_type, "mac": mac}
    finally:
        await client.close()


class JupiterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtungsdialog."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            try:
                info = await _probe(
                    host, user_input[CONF_PORT], user_input[CONF_UNIT_ID]
                )
            except ModbusError as err:
                _LOGGER.debug("Verbindungstest fehlgeschlagen: %s", err)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info["mac"] or host)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: host}
                )
                model = DEVICE_TYPES.get(info["device_type"], "Jupiter C+")
                return self.async_create_entry(
                    title=f"Marstek {model}", data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return JupiterOptionsFlow()


class JupiterOptionsFlow(OptionsFlow):
    """Abfragetakt und Feinheiten nachtraeglich aendern."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        data = self.config_entry.data

        def current(key: str, default: Any) -> Any:
            return options.get(key, data.get(key, default))

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_FAST_INTERVAL,
                    default=current(CONF_FAST_INTERVAL, DEFAULT_FAST_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(5, 300)),
                vol.Optional(
                    CONF_SLOW_INTERVAL,
                    default=current(CONF_SLOW_INTERVAL, DEFAULT_SLOW_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(30, 3600)),
                vol.Optional(
                    CONF_STATUS_INTERVAL,
                    default=current(CONF_STATUS_INTERVAL, DEFAULT_STATUS_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(30, 3600)),
                vol.Optional(
                    CONF_TIMEOUT,
                    default=current(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                ): vol.All(vol.Coerce(float), vol.Range(1, 30)),
                vol.Optional(
                    CONF_MESSAGE_WAIT,
                    default=current(CONF_MESSAGE_WAIT, DEFAULT_MESSAGE_WAIT),
                ): vol.All(vol.Coerce(float), vol.Range(0, 2)),
                vol.Optional(
                    CONF_ERROR_FALLBACK,
                    description={
                        "suggested_value": current(CONF_ERROR_FALLBACK, None)
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
