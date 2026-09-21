#!/usr/bin/env python3
"""Erzeugt strings.json und die Uebersetzungen aus einer Quelle.

Damit koennen die Schluessel zwischen den Sprachen nicht auseinanderlaufen.
Das Skript gehoert nicht zur Integration, es ist ein Werkzeug fuer das
Repository.
"""

import json
import os

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "custom_components", "marstek_jupiter")

# key: (deutsch, englisch)
SENSOR_NAMES = {
    **{f"pv{n}_voltage": (f"PV{n} Spannung", f"PV{n} voltage") for n in range(1, 5)},
    **{f"pv{n}_current": (f"PV{n} Strom", f"PV{n} current") for n in range(1, 5)},
    **{f"pv{n}_power": (f"PV{n} Leistung", f"PV{n} power") for n in range(1, 5)},
    "pv_total_power": ("PV Gesamtleistung", "PV total power"),
    "grid_power": ("Netzleistung", "Grid power"),
    "battery_power": ("Batterieleistung (berechnet)", "Battery power (calculated)"),
    "pv_energy": ("PV Energie", "PV energy"),
    "battery_charge_energy": ("Batterie geladen", "Battery charged"),
    "battery_discharge_energy": ("Batterie entladen", "Battery discharged"),
    "battery_voltage": ("Batteriespannung", "Battery voltage"),
    "battery_soc": ("Ladezustand", "State of charge"),
    "daily_generation": ("Tagesertrag", "Daily generation"),
    "monthly_generation": ("Monatsertrag", "Monthly generation"),
    "daily_grid": ("Tageseinspeisung", "Daily grid feed-in"),
    "monthly_grid": ("Monatseinspeisung", "Monthly grid feed-in"),
    "cell_voltage_max": ("Zellspannung max", "Cell voltage max"),
    "cell_voltage_min": ("Zellspannung min", "Cell voltage min"),
    "cell_voltage_delta": ("Zellspannungs-Differenz", "Cell voltage delta"),
    "temperature": ("Temperatur (unbestätigt)", "Temperature (unconfirmed)"),
    "temperature_raw": ("Temperatur roh (unbestätigt)",
                        "Temperature raw (unconfirmed)"),
    "error_code": ("Fehlercode", "Error code"),
    "error_text": ("Fehlercode Klartext", "Error description"),
    "device_id": ("Geräte-ID", "Device ID"),
    "ems_version": ("EMS-Version", "EMS version"),
    "inv_version": ("INV-Version", "Inverter version"),
    "mppt_version": ("MPPT-Version", "MPPT version"),
    "bms_version": ("BMS-Version", "BMS version"),
    "screen_version": ("Display-Version", "Display version"),
    "device_type": ("Gerätetyp (Code)", "Device type (code)"),
    "device_type_text": ("Gerätetyp", "Device type"),
    "mac_address": ("MAC-Adresse", "MAC address"),
    "comm_firmware": ("Kommunikationsmodul-Firmware", "Communication module firmware"),
    "diag_0012": ("Diagnose 0x0012", "Diagnostic 0x0012"),
    "diag_0023": ("Diagnose 0x0023", "Diagnostic 0x0023"),
}

BINARY_NAMES = {
    **{f"pv{n}_status": (f"PV{n} Status", f"PV{n} status") for n in range(1, 5)},
    "inverter_status": ("Wechselrichter Status", "Inverter status"),
}

CONFIG = {
    "de": {
        "step": {
            "user": {
                "title": "Marstek Jupiter C+",
                "description": (
                    "IP-Adresse des RS485-WLAN-Umsetzers (Elfin EW11/EE11). "
                    "Der Umsetzer muss stehen auf 115200 Bd, 8/None/1, "
                    "Protokoll Modbus, Half Duplex, TCP-Server, Port 502."
                ),
                "data": {
                    "host": "IP-Adresse",
                    "port": "Port",
                    "unit_id": "Modbus-Adresse des Geräts",
                    "adopt_legacy": "Bisherige Entity-IDs übernehmen",
                },
                "data_description": {
                    "adopt_legacy": (
                        "Übernimmt die IDs einer früheren YAML-Lösung, damit "
                        "Verlauf, Statistik, Dashboards und Automationen "
                        "weiterlaufen. Dafür muss das alte Paket vorher "
                        "entfernt und Home Assistant neu gestartet sein."
                    )
                },
            }
        },
        "error": {
            "cannot_connect": (
                "Keine Antwort. IP-Adresse, Port und die Einstellungen des "
                "Umsetzers prüfen - und ob noch ein anderes Programm auf dem "
                "Umsetzer hängt; er verträgt nur eine Verbindung."
            )
        },
        "abort": {"already_configured": "Dieses Gerät ist bereits eingerichtet."},
    },
    "en": {
        "step": {
            "user": {
                "title": "Marstek Jupiter C+",
                "description": (
                    "IP address of the RS485-to-WiFi bridge (Elfin EW11/EE11). "
                    "The bridge must be set to 115200 baud, 8/None/1, Modbus "
                    "protocol, half duplex, TCP server, port 502."
                ),
                "data": {
                    "host": "IP address",
                    "port": "Port",
                    "unit_id": "Modbus unit ID",
                    "adopt_legacy": "Adopt existing entity IDs",
                },
                "data_description": {
                    "adopt_legacy": (
                        "Takes over the IDs of a previous YAML setup so that "
                        "history, statistics, dashboards and automations keep "
                        "working. The old package must be removed and Home "
                        "Assistant restarted first."
                    )
                },
            }
        },
        "error": {
            "cannot_connect": (
                "No response. Check the IP address, port and bridge settings - "
                "and whether another program is still connected; the bridge "
                "accepts only one connection."
            )
        },
        "abort": {"already_configured": "This device is already configured."},
    },
}

OPTIONS = {
    "de": {
        "step": {
            "init": {
                "title": "Abfragetakt",
                "description": (
                    "Der Umsetzer bearbeitet immer nur eine Anfrage. Lieber "
                    "wenige Sensoren langsam als viele schnell."
                ),
                "data": {
                    "fast_interval": "Schneller Takt (Leistungen, Ladezustand)",
                    "slow_interval": "Langsamer Takt (Zähler, Versionen)",
                    "status_interval": "Statusflags",
                    "timeout": "Zeitüberschreitung in Sekunden",
                    "message_wait": "Pause zwischen zwei Anfragen in Sekunden",
                    "error_fallback_entity": "MQTT-Fehlersensor als zweite Quelle",
                },
                "data_description": {
                    "timeout": (
                        "Unter 5 Sekunden wird es kritisch: gibt Home Assistant "
                        "zu früh auf, trifft die Antwort trotzdem ein und wird "
                        "der nächsten Anfrage zugeordnet."
                    ),
                    "error_fallback_entity": (
                        "Optional. Steht das Modbus-Register auf 0, wird dieser "
                        "Sensor herangezogen - er hält einen Fehlercode länger."
                    ),
                },
            }
        }
    },
    "en": {
        "step": {
            "init": {
                "title": "Polling intervals",
                "description": (
                    "The bridge handles one request at a time. Few sensors "
                    "polled slowly beats many polled fast."
                ),
                "data": {
                    "fast_interval": "Fast interval (power, state of charge)",
                    "slow_interval": "Slow interval (counters, versions)",
                    "status_interval": "Status flags",
                    "timeout": "Timeout in seconds",
                    "message_wait": "Pause between requests in seconds",
                    "error_fallback_entity": "MQTT error sensor as second source",
                },
                "data_description": {
                    "timeout": (
                        "Below 5 seconds this gets risky: if Home Assistant "
                        "gives up too early, the answer still arrives and gets "
                        "attributed to the next request."
                    ),
                    "error_fallback_entity": (
                        "Optional. When the Modbus register reads 0, this "
                        "sensor is used instead - it holds an error code longer."
                    ),
                },
            }
        }
    },
}

SERVICES = {
    "de": {
        "register_dump": {
            "name": "Registerabzug",
            "description": (
                "Legt einen vollständigen Abzug des lesbaren Registerraums an. "
                "Vor und nach einem Firmware-Update laufen lassen und "
                "vergleichen - Marstek veröffentlicht keine Changelogs."
            ),
            "fields": {
                "label": {
                    "name": "Bezeichnung",
                    "description": "Namensteil der Ausgabedatei, z. B. vor-update.",
                },
                "sweep": {
                    "name": "Grobsuche",
                    "description": (
                        "Tastet zusätzlich den gesamten Adressraum ab. Dauert "
                        "deutlich länger und findet Blöcke, keine einzelnen "
                        "Register zwischen toten Nachbarn."
                    ),
                },
            },
        },
        "read_register": {
            "name": "Register lesen",
            "description": (
                "Liest bis zu 8 Holding-Register. Läuft über dieselbe "
                "Verbindung wie die laufende Abfrage, kann sich also nicht mit "
                "ihr überschneiden."
            ),
            "fields": {
                "address": {"name": "Adresse", "description": "Dezimal oder 0x-Notation."},
                "count": {"name": "Anzahl", "description": "1 bis 8. Mehr lehnt das Gerät ab."},
                "data_type": {"name": "Datentyp", "description": "Wie die Rohwerte gedeutet werden."},
            },
        },
    },
    "en": {
        "register_dump": {
            "name": "Register dump",
            "description": (
                "Creates a full snapshot of the readable register space. Run it "
                "before and after a firmware update and compare - Marstek does "
                "not publish changelogs."
            ),
            "fields": {
                "label": {"name": "Label", "description": "Part of the output file name."},
                "sweep": {
                    "name": "Coarse sweep",
                    "description": (
                        "Also probes the whole address space. Takes much longer "
                        "and finds blocks, not single registers between dead "
                        "neighbours."
                    ),
                },
            },
        },
        "read_register": {
            "name": "Read register",
            "description": (
                "Reads up to 8 holding registers over the same connection as "
                "the running poll, so the two cannot collide."
            ),
            "fields": {
                "address": {"name": "Address", "description": "Decimal or 0x notation."},
                "count": {"name": "Count", "description": "1 to 8. The device rejects more."},
                "data_type": {"name": "Data type", "description": "How to interpret the raw words."},
            },
        },
    },
}


def build(lang: str) -> dict:
    index = 0 if lang == "de" else 1
    return {
        "config": CONFIG[lang],
        "options": OPTIONS[lang],
        "services": SERVICES[lang],
        "entity": {
            "sensor": {
                key: {"name": names[index]} for key, names in SENSOR_NAMES.items()
            },
            "binary_sensor": {
                key: {"name": names[index]} for key, names in BINARY_NAMES.items()
            },
        },
    }


def main() -> None:
    os.makedirs(os.path.join(BASE, "translations"), exist_ok=True)
    english = build("en")
    german = build("de")
    targets = {
        os.path.join(BASE, "strings.json"): english,
        os.path.join(BASE, "translations", "en.json"): english,
        os.path.join(BASE, "translations", "de.json"): german,
    }
    for path, payload in targets.items():
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        print("geschrieben:", path)


if __name__ == "__main__":
    main()
