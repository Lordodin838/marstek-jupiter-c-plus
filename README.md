<p align="center">
  <img src="https://raw.githubusercontent.com/Lordodin838/marstek-jupiter-c-plus-hacs/main/custom_components/marstek_jupiter/brand/icon@2x.png" alt="Logo" width="112">
</p>

<h1 align="center">Marstek Jupiter C+</h1>

<p align="center">
  Local Home Assistant integration for the Marstek Jupiter C+<br>
  via Modbus TCP (Elfin EW11 / EE11)
</p>

<p align="center">
  <a href="https://github.com/Lordodin838/marstek-jupiter-c-plus-hacs/releases"><img src="https://img.shields.io/github/v/release/Lordodin838/marstek-jupiter-c-plus-hacs?label=Version" alt="Version"></a>
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5" alt="HACS"></a>
  <a href="https://github.com/Lordodin838/marstek-jupiter-c-plus-hacs/actions/workflows/validate.yml"><img src="https://img.shields.io/github/actions/workflow/status/Lordodin838/marstek-jupiter-c-plus-hacs/validate.yml?label=Tests" alt="Tests"></a>
</p>

<p align="center">
  <b>🇬🇧 English</b> · <a href="https://github.com/Lordodin838/marstek-jupiter-c-plus-hacs/blob/main/README.de.md">🇩🇪 Deutsch</a>
</p>

---

## At a glance

- ✅ **Set up in the UI** – no YAML, no cloud, no extra packages
- ⚡ **Power, state of charge and grid every 10 s** – from *one*
  request, so all values describe the same moment
- 🔋 **Energy counters for the Energy dashboard** – PV, battery charged
  and discharged, no Riemann helpers needed
- 🛡️ **Robust against the Elfin's quirks** – stray and late responses
  are detected and discarded
- 🧾 **Error code in plain text** – as a notice under *Repairs* and as an event for push notifications
- 🔁 **Migrate from YAML without losing data** – existing entity IDs
  and their history are adopted

Tested with firmware 142.37.213.110, device type Jupiter C 800 W.

---

## Installation

**Via HACS**

1. HACS → ⋮ → *Custom repositories*
2. Add `https://github.com/Lordodin838/marstek-jupiter-c-plus-hacs`,
   category *Integration*
3. Download *Marstek Jupiter C+* and restart Home Assistant
4. *Settings → Devices & services → Add integration →
   Marstek Jupiter C+*
5. Enter the IP address of the converter – done

Home Assistant then reports new versions on its own under
*Settings → Updates*.

**Elfin settings**

| Setting | Value |
|---|---|
| Serial port | 115200 baud, 8 / None / 1 |
| Protocol | Modbus |
| Flow control | Half Duplex |
| CLI | Disabled |
| Network | TCP Server, port 502, route UART |

> ⚠️ The converter handles **only one connection**. Do not run a second
> program or a second Modbus package alongside.

<details>
<summary><b>Manual installation</b></summary>

Copy the folder `custom_components/marstek_jupiter` to
`config/custom_components/` and restart.

**The folder must be named exactly `marstek_jupiter`.** Home Assistant
finds the entity names through the folder name, not through
`manifest.json`. If it is named differently – for example
`Marstek Jupiter C+` after unpacking an archive – all values still work,
but every entity is named after the device and gets an ID like
`sensor.marstek_jupiter_c_15`. The integration logs a warning in that
case. Installing via HACS avoids this entirely.

</details>

---

## Entities

46 entities on the device “Marstek Jupiter C+”. Each one can be renamed
in the UI.

**Power and battery** · every 10 s

| Entity | Unit |
|---|---|
| PV1–4 power | W |
| PV1–4 voltage | V |
| PV1–4 current | A |
| PV total power | W |
| Grid power ¹ | W |
| Battery power (calculated) ² | W |
| State of charge | % |
| Battery voltage | V |
| Temperature (unconfirmed) | °C |

¹ positive = export, negative = import<br>
² PV − grid power; positive = charging, negative = discharging

**Energy** · for the Energy dashboard

| Entity | Source | Unit |
|---|---|---|
| PV energy | accumulated | kWh |
| Battery charged | accumulated | kWh |
| Battery discharged | accumulated | kWh |
| Daily / monthly generation | device counter | kWh |
| Daily / monthly grid feed-in | device counter | kWh |

**Cells** · every 60 s

| Entity | Unit |
|---|---|
| Cell voltage max / min | V |
| Cell voltage delta | mV |

Below 50 mV the pack is healthy; above 100 mV a cell is drifting away.

**Status and diagnostics**

| Entity | Interval |
|---|---|
| Error code, error description | 60 s |
| PV1–4 status, inverter status | 300 s |
| EMS, inverter, MPPT, BMS, display version | 60 s |
| Device ID, device type | 60 s |
| MAC address, communication module firmware | 1 h |

Disabled by default: *Device type (code)* and *Temperature raw*.

<details>
<summary><b>Register map</b></summary>

| Register | Content |
|---|---|
| `0x0001`–`0x000C` | PV1–4 voltage, current, power each |
| `0x000D` | Grid power, **int16** |
| `0x000E` | Temperature (unconfirmed) |
| `0x000F` | Battery voltage |
| `0x0010` | State of charge |
| `0x0011` | Error code (decimal; the manual lists it in hex) |
| `0x0013`–`0x001A` | Daily/monthly generation, daily/monthly feed-in, uint32 |
| `0x001B` | Device ID |
| `0x001C`–`0x001F`, `0x0022` | EMS, INV, MPPT, BMS, display |
| `0x0020` / `0x0021` | Cell voltage max / min |
| `0x0025` | Device type |
| `0x1004`–`0x1008` | PV1–4 status, inverter status |
| `0x1100`–`0x1105` | MAC address, ASCII |
| `0x1200`–`0x1205` | Communication module firmware, ASCII |

Read but without an entity of their own: `0x0012`, `0x0023`, `0x0024`
and the status flags `0x1000`–`0x1003`, `0x1009`, `0x100A`. Use the
services below to inspect them.

**Not provided by the device:** no register for DC battery power
(`0x000E` is not it), none for depth of discharge (only via hm2mqtt), no
individual voltages of the 16 cells. `0x4000`–`0x43FF` is write-only.
This integration never writes to the device.

</details>

---

## Energy dashboard

| Section | Entity |
|---|---|
| Solar | PV energy |
| Battery – energy going in | Battery charged |
| Battery – energy coming out | Battery discharged |
| Battery – state of charge | State of charge |

The integration accumulates these three counters itself from the 10 s
values. It only counts rounds in which the power values were freshly
read; if the connection drops for more than 60 s, the gap is not
extrapolated. The counters survive restarts. “Charged” includes the
conversion losses (about 6 %).

---

## Error notifications

When the device reports an error code, Home Assistant shows it under
*Settings → Repairs*, with the plain-text description from the manual.
The notice disappears by itself once the code is back to 0.

The integration also fires the event `marstek_jupiter_error` on every
change – use it for a push notification:

```yaml
triggers:
  - trigger: event
    event_type: marstek_jupiter_error
    event_data:
      active: true
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "Jupiter C+ error {{ trigger.event.data.code_hex }}"
      message: "{{ trigger.event.data.description }}"
```

| Field | Content |
|---|---|
| `active` | `true` = error present, `false` = cleared |
| `code` / `code_hex` | e.g. `1062` / `0x426` |
| `description` | plain text from the manual's table |
| `previous_code` | code before the change |

---

## Options

*Settings → Devices & services → Marstek Jupiter C+ → Configure*

| Option | Default |
|---|---|
| Fast interval (power, state of charge) | 10 s |
| Slow interval (counters, versions) | 60 s |
| Status flags | 300 s |
| Timeout | 5 s |
| Pause between requests | 0.15 s |
| MQTT error sensor as second source | – |

> Rule of thumb: **few requests slowly beat many requests fast.** Do not
> set the timeout below 5 s – otherwise a late response arrives and is
> matched to the next request.

---

## Services

<details>
<summary><b><code>marstek_jupiter.register_dump</code> – register dump</b></summary>

Full dump of the readable register space, for example before and after
a firmware update. Marstek does not publish changelogs.

```yaml
action: marstek_jupiter.register_dump
data:
  label: before-update
  sweep: false
```

Results are written as `.json` and `.txt` to `config/marstek_jupiter/`.
The dump uses the same connection as the regular polling and cannot
collide with it. Every value is read three times; uncertain values are
marked `NEIN` in the text file.

`sweep: true` additionally probes the whole address space. It finds
blocks, but not isolated registers between dead neighbours.

</details>

<details>
<summary><b><code>marstek_jupiter.read_register</code> – single read</b></summary>

```yaml
action: marstek_jupiter.read_register
data:
  address: 42
  count: 1
  data_type: uint16
response_variable: result
```

</details>

---

## Migrating from a YAML setup

<details>
<summary><b>Adopt existing entity IDs</b></summary>

The integration adopts the entity IDs of an earlier Modbus and template
configuration. History, statistics, dashboards and automations keep
working without changes.

**Order matters:**

1. Disable the old package, e.g. rename `jupiter_c_plus_modbus.yaml` →
   `jupiter_c_plus_modbus.yaml.off`, together with its template
   sensors.
2. **Restart Home Assistant.** Only then are the IDs free.
3. Add the integration and leave *Adopt existing entity IDs* ticked.

If the old package is still active, nothing is adopted and a warning is
logged.

| previous (unique_id) | becomes |
|---|---|
| `jupiter_modbus_pv1..4_voltage/current/power` | PV1–4 voltage/current/power |
| `jupiter_modbus_grid_power`, `_battery_voltage`, `_battery_soc` | Grid power, battery voltage, state of charge |
| `jupiter_modbus_daily/monthly_generation/grid` | Device counters |
| `jupiter_modbus_cell_voltage_max/min` | Cell voltages |
| `jupiter_modbus_*_version`, `_device_id`, `_device_type`, `_mac`, `_comm_version` | Diagnostics |
| `jupiter_diag_0011` | Error code |
| `jupiter_modbus_pv1..4_status`, `_inv_status` | Status |
| `jupiter_modbus_total_pv_power` (template) | PV total power |
| `jupiter_battery_power_calculated` (template) | Battery power (calculated) |
| `jupiter_cell_voltage_delta` (template) | Cell voltage delta |
| `jupiter_error_code_text` (template) | Error description |
| `jupiter_temperature_filtered` (template) | Temperature |
| `jupiter_modbus_device_type_text` (template) | Device type |

</details>

---

## Troubleshooting

<details>
<summary><b>All entities are called “Marstek Jupiter C+”</b></summary>

The folder name is wrong, see *Manual installation*. Rename the folder
to `marstek_jupiter` and restart.

</details>

<details>
<summary><b>Log: “… bisherige Entitaeten sind noch aktiv …”</b></summary>

(The integration logs in German: “N existing entities are still
active”.) The old YAML package is still loaded, so two programs are
polling the same converter. Rename the package to `.off` and restart.

</details>

<details>
<summary><b>Entities stay “unavailable”</b></summary>

A read block failed three times in a row. Check:

1. Is a second program connected to the converter?
2. Is the timeout below 5 s?
3. Are the Elfin settings correct?

The affected block is named in the log and in the integration's
diagnostics.

</details>

<details>
<summary><b>Modbus exception 2 or 3</b></summary>

**3:** A request covers more than 8 registers.
**2:** A request runs past the end of a valid range – after a firmware
update the register map may have shifted. Compare `register_dump`
before and after.

</details>

---

## Technical background

<details>
<summary><b>Why not Home Assistant's Modbus integration?</b></summary>

The Elfin has two quirks that break an ordinary Modbus configuration:

1. **It handles only one request at a time.** If two arrive in quick
   succession, it mixes up the responses – visible as *the right value
   in the wrong sensor*, such as a state of charge of 3308 %.
2. **It passes through foreign responses with a matching transaction
   ID.**

The integration therefore brings its own transport: one connection, one
lock, strict checks of transaction ID, protocol ID, unit ID and length.
It also reads in blocks instead of register by register:

| | YAML, single registers | this integration |
|---|---|---|
| Requests per minute | about 48 | **15.4** |
| PV, grid, state of charge | separate requests | **one request** |
| PV voltages and currents | 121 s | 10 s |

Because the calculated battery power is the difference between PV and
grid power, both have to come from the same moment – otherwise the
result fluctuates for no physical reason.

</details>

<details>
<summary><b>Plausibility filter</b></summary>

Raw values outside physically possible limits are discarded and the
last good value is kept. The limits are in `const.py` under
`VALID_RANGES`.

Grid power is read as **int16**. The widely used community map lists
`0x000D` as unsigned – grid import would then show up as about
65,000 W.

</details>

<details>
<summary><b>Device quirks</b></summary>

- **Grid power oscillates.** This is real: the CT control follows the
  house load and overshoots. A Shelly at the grid connection shows the
  same. Don't filter it out.
- **After a firmware update** the phase detection may be 0 – run it
  once more via hm2mqtt.
- **`0x0011` is the error code**, not the battery current. The register
  returns in decimal what the manual lists in hex (1062 = 0x426).
- **`0x0020` / `0x0021` are cell voltages**, not temperatures: value
  times 16 cells equals the battery voltage.

</details>

<details>
<summary><b>Tests</b></summary>

`python3 tests/test_integration.py` runs without Home Assistant
(Python 3.11 or newer). A simulator reproduces the device's quirks: at
most 8 registers, exceptions when a range is exceeded, stray and late
responses. Among other things it checks that:

- every required address lies in a read block
- a stray response does not corrupt the state of charge
- 20 concurrent requests stay separate
- the energy counters are correct and do not bridge outages

</details>

---

MIT license · [Report an issue](https://github.com/Lordodin838/marstek-jupiter-c-plus-hacs/issues)
