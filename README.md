<p align="center">
  <img src="https://raw.githubusercontent.com/Lordodin838/marstek-jupiter-c-plus-hacs/main/custom_components/marstek_jupiter/brand/icon@2x.png" alt="Logo" width="112">
</p>

<h1 align="center">Marstek Jupiter C+</h1>

<p align="center">
  Lokale Home-Assistant-Integration für den Marstek Jupiter C+<br>
  über Modbus TCP (Elfin EW11 / EE11)
</p>

<p align="center">
  <a href="https://github.com/Lordodin838/marstek-jupiter-c-plus-hacs/releases"><img src="https://img.shields.io/github/v/release/Lordodin838/marstek-jupiter-c-plus-hacs?label=Version" alt="Version"></a>
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5" alt="HACS"></a>
  <a href="https://github.com/Lordodin838/marstek-jupiter-c-plus-hacs/actions/workflows/validate.yml"><img src="https://img.shields.io/github/actions/workflow/status/Lordodin838/marstek-jupiter-c-plus-hacs/validate.yml?label=Tests" alt="Tests"></a>
</p>

---

## Auf einen Blick

- ✅ **Einrichtung über die Oberfläche** – keine YAML, keine Cloud, keine
  Zusatzpakete
- ⚡ **Leistung, Ladezustand und Netz alle 10 s** – aus *einer* Anfrage,
  also aus demselben Augenblick
- 🔋 **Energiezähler fürs Energie-Dashboard** – PV, Batterie geladen und
  entladen, ohne Riemann-Helfer
- 🛡️ **Robust gegen die Eigenheiten des Elfin** – verirrte und
  verspätete Antworten werden erkannt und verworfen
- 🧾 **Fehlercode im Klartext** – nach der Tabelle aus dem Handbuch
- 🔁 **Umstieg von YAML ohne Datenverlust** – bisherige Entity-IDs samt
  Verlauf werden übernommen

Getestet mit Firmware 142.37.213.110, Gerätetyp Jupiter C 800 W.

---

## Installation

**Über HACS**

1. HACS → ⋮ → *Benutzerdefinierte Repositories*
2. `https://github.com/Lordodin838/marstek-jupiter-c-plus-hacs`
   eintragen, Kategorie *Integration*
3. *Marstek Jupiter C+* herunterladen und Home Assistant neu starten
4. *Einstellungen → Geräte & Dienste → Integration hinzufügen →
   Marstek Jupiter C+*
5. IP-Adresse des Umsetzers eingeben – fertig

Neue Versionen meldet Home Assistant danach von selbst unter
*Einstellungen → Updates*.

**Einstellungen des Elfin**

| Einstellung | Wert |
|---|---|
| Serielle Schnittstelle | 115200 Bd, 8 / None / 1 |
| Protokoll | Modbus |
| Flow Control | Half Duplex |
| CLI | Disabled |
| Netzwerk | TCP Server, Port 502, Route UART |

> ⚠️ Der Umsetzer verträgt **nur eine Verbindung**. Kein zweites
> Programm und kein zweites Modbus-Paket parallel betreiben.

<details>
<summary><b>Installation von Hand</b></summary>

Den Ordner `custom_components/marstek_jupiter` nach
`config/custom_components/` kopieren und neu starten.

**Der Ordner muss exakt `marstek_jupiter` heißen.** Home Assistant
findet die Entitätsnamen über den Ordnernamen, nicht über die
`manifest.json`. Heißt er anders – etwa `Marstek Jupiter C+` nach dem
Entpacken –, laufen zwar alle Werte, aber jede Entität heißt wie das
Gerät und bekommt eine ID wie `sensor.marstek_jupiter_c_15`. Die
Integration schreibt in diesem Fall eine Warnung ins Protokoll. Über
HACS installiert kann das nicht passieren.

</details>

---

## Entitäten

46 Entitäten am Gerät „Marstek Jupiter C+". Jede lässt sich in der
Oberfläche umbenennen.

**Leistung und Batterie** · alle 10 s

| Entität | Einheit |
|---|---|
| PV1–4 Leistung | W |
| PV1–4 Spannung | V |
| PV1–4 Strom | A |
| PV Gesamtleistung | W |
| Netzleistung ¹ | W |
| Batterieleistung (berechnet) ² | W |
| Ladezustand | % |
| Batteriespannung | V |
| Temperatur (unbestätigt) | °C |

¹ positiv = Abgabe, negativ = Bezug<br>
² PV − Netzleistung; positiv = laden, negativ = entladen

**Energie** · für das Energie-Dashboard

| Entität | Quelle | Einheit |
|---|---|---|
| PV Energie | aufsummiert | kWh |
| Batterie geladen | aufsummiert | kWh |
| Batterie entladen | aufsummiert | kWh |
| Tages- / Monatsertrag | Gerätezähler | kWh |
| Tages- / Monatseinspeisung | Gerätezähler | kWh |

**Zellen** · alle 60 s

| Entität | Einheit |
|---|---|
| Zellspannung max / min | V |
| Zellspannungs-Differenz | mV |

Unter 50 mV Differenz ist ein gesunder Pack, über 100 mV läuft eine
Zelle davon.

**Status und Diagnose**

| Entität | Takt |
|---|---|
| Fehlercode, Fehlercode Klartext | 60 s |
| PV1–4 Status, Wechselrichter Status | 300 s |
| EMS-, INV-, MPPT-, BMS-, Display-Version | 60 s |
| Geräte-ID, Gerätetyp | 60 s |
| MAC-Adresse, Kommunikationsmodul-Firmware | 1 h |

Standardmäßig abgeschaltet: *Gerätetyp (Code)* und *Temperatur roh*.

<details>
<summary><b>Registerkarte</b></summary>

| Register | Inhalt |
|---|---|
| `0x0001`–`0x000C` | PV1–4 je Spannung, Strom, Leistung |
| `0x000D` | Netzleistung, **int16** |
| `0x000E` | Temperatur (unbestätigt) |
| `0x000F` | Batteriespannung |
| `0x0010` | Ladezustand |
| `0x0011` | Fehlercode (dezimal, Handbuch hexadezimal) |
| `0x0013`–`0x001A` | Tages-/Monatsertrag, Tages-/Monatseinspeisung, uint32 |
| `0x001B` | Geräte-ID |
| `0x001C`–`0x001F`, `0x0022` | EMS, INV, MPPT, BMS, Display |
| `0x0020` / `0x0021` | Zellspannung max / min |
| `0x0025` | Gerätetyp |
| `0x1004`–`0x1008` | PV1–4 Status, Wechselrichter Status |
| `0x1100`–`0x1105` | MAC-Adresse, ASCII |
| `0x1200`–`0x1205` | Firmware Kommunikationsmodul, ASCII |

Mitgelesen, aber ohne eigene Entität: `0x0012`, `0x0023`, `0x0024` und
die Statusflags `0x1000`–`0x1003`, `0x1009`, `0x100A`. Wer sie
untersuchen will, nimmt die Dienste unten.

**Was das Gerät nicht liefert:** kein Register für die
DC-Batterieleistung (`0x000E` ist es nicht), keines für die Entladetiefe
(läuft nur über hm2mqtt), keine Einzelspannungen der 16 Zellen.
`0x4000`–`0x43FF` ist write-only. Diese Integration schreibt nicht ins
Gerät.

</details>

---

## Energie-Dashboard

| Bereich | Entität |
|---|---|
| Solar | PV Energie |
| Batterie – in die Batterie | Batterie geladen |
| Batterie – aus der Batterie | Batterie entladen |
| Batterie – Ladezustand | Ladezustand |

Die drei Zähler summiert die Integration selbst aus den 10-s-Werten. Sie
zählt nur Runden, in denen die Leistungen frisch gelesen wurden; fällt
die Verbindung länger als 60 s aus, wird die Lücke nicht hochgerechnet.
Der Stand überlebt Neustarts. „Geladen“ enthält die Wandlungsverluste
(rund 6 %).

---

## Einstellungen

*Einstellungen → Geräte & Dienste → Marstek Jupiter C+ → Konfigurieren*

| Einstellung | Standard |
|---|---|
| Schneller Takt (Leistungen, Ladezustand) | 10 s |
| Langsamer Takt (Zähler, Versionen) | 60 s |
| Statusflags | 300 s |
| Zeitüberschreitung | 5 s |
| Pause zwischen zwei Anfragen | 0,15 s |
| MQTT-Fehlersensor als zweite Quelle | – |

> Faustregel: **lieber wenige Anfragen langsam als viele schnell.** Die
> Zeitüberschreitung nicht unter 5 s setzen – sonst trifft eine späte
> Antwort ein und wird der nächsten Anfrage zugeordnet.

---

## Dienste

<details>
<summary><b><code>marstek_jupiter.register_dump</code> – Registerabzug</b></summary>

Vollständiger Abzug des lesbaren Registerraums, zum Beispiel vor und
nach einem Firmware-Update. Marstek veröffentlicht keine Changelogs.

```yaml
action: marstek_jupiter.register_dump
data:
  label: vor-update
  sweep: false
```

Ergebnis als `.json` und `.txt` in `config/marstek_jupiter/`. Der Abzug
läuft über dieselbe Verbindung wie die laufende Abfrage und kann sich
mit ihr nicht überschneiden. Jeder Wert wird dreimal gelesen; unsichere
Werte stehen mit `NEIN` in der Textdatei.

`sweep: true` tastet zusätzlich den ganzen Adressraum ab. Das findet
Blöcke, aber keine Einzelgänger zwischen toten Nachbarn.

</details>

<details>
<summary><b><code>marstek_jupiter.read_register</code> – Einzelabfrage</b></summary>

```yaml
action: marstek_jupiter.read_register
data:
  address: 42
  count: 1
  data_type: uint16
response_variable: ergebnis
```

</details>

---

## Umstieg von einer YAML-Lösung

<details>
<summary><b>Bisherige Entity-IDs übernehmen</b></summary>

Die Integration übernimmt die Entity-IDs einer früheren Modbus- und
Template-Konfiguration. Verlauf, Statistik, Dashboards und Automationen
laufen dann ohne Nacharbeit weiter.

**Reihenfolge:**

1. Altes Paket deaktivieren, zum Beispiel `jupiter_c_plus_modbus.yaml`
   → `jupiter_c_plus_modbus.yaml.aus`, samt der zugehörigen
   Template-Sensoren.
2. **Home Assistant neu starten.** Erst dann sind die IDs frei.
3. Integration hinzufügen, Haken bei *Bisherige Entity-IDs übernehmen*
   stehen lassen.

Ist das alte Paket noch aktiv, übernimmt die Integration nichts und
schreibt eine Warnung ins Protokoll.

| bisher (unique_id) | wird zu |
|---|---|
| `jupiter_modbus_pv1..4_voltage/current/power` | PV1–4 Spannung/Strom/Leistung |
| `jupiter_modbus_grid_power`, `_battery_voltage`, `_battery_soc` | Netzleistung, Batteriespannung, Ladezustand |
| `jupiter_modbus_daily/monthly_generation/grid` | Gerätezähler |
| `jupiter_modbus_cell_voltage_max/min` | Zellspannungen |
| `jupiter_modbus_*_version`, `_device_id`, `_device_type`, `_mac`, `_comm_version` | Diagnose |
| `jupiter_diag_0011` | Fehlercode |
| `jupiter_modbus_pv1..4_status`, `_inv_status` | Status |
| `jupiter_modbus_total_pv_power` (template) | PV Gesamtleistung |
| `jupiter_battery_power_calculated` (template) | Batterieleistung (berechnet) |
| `jupiter_cell_voltage_delta` (template) | Zellspannungs-Differenz |
| `jupiter_error_code_text` (template) | Fehlercode Klartext |
| `jupiter_temperature_filtered` (template) | Temperatur |
| `jupiter_modbus_device_type_text` (template) | Gerätetyp |

</details>

---

## Fehlersuche

<details>
<summary><b>Alle Entitäten heißen „Marstek Jupiter C+"</b></summary>

Der Ordnername stimmt nicht, siehe *Installation von Hand*. Ordner nach
`marstek_jupiter` umbenennen und neu starten.

</details>

<details>
<summary><b>„N bisherige Entitäten sind noch aktiv" im Protokoll</b></summary>

Das alte YAML-Paket ist noch geladen, und zwei Programme fragen
denselben Umsetzer ab. Paket auf `.aus` umbenennen und neu starten.

</details>

<details>
<summary><b>Entitäten bleiben „nicht verfügbar"</b></summary>

Ein Leseblock ist dreimal hintereinander gescheitert. Prüfen:

1. Hängt ein zweites Programm am Umsetzer?
2. Steht die Zeitüberschreitung unter 5 s?
3. Stimmen die Einstellungen des Elfin?

Welcher Block betroffen ist, steht im Protokoll und in den
Diagnosedaten der Integration.

</details>

<details>
<summary><b>Modbus-Exception 2 oder 3</b></summary>

**3:** Eine Anfrage umfasst mehr als 8 Register.
**2:** Eine Anfrage reicht über das Ende eines gültigen Bereichs – nach
einem Firmware-Update kann sich die Registerkarte verschoben haben.
`register_dump` vorher und nachher vergleichen.

</details>

---

## Technischer Hintergrund

<details>
<summary><b>Warum nicht die Modbus-Integration von Home Assistant?</b></summary>

Der Elfin hat zwei Eigenheiten, an denen eine gewöhnliche
Modbus-Konfiguration scheitert:

1. **Er bearbeitet immer nur eine Anfrage.** Kommen zwei kurz
   hintereinander, ordnet er Antworten falsch zu – sichtbar als
   *richtiger Wert im falschen Sensor*, etwa ein Ladezustand von 3308 %.
2. **Er reicht fremde Antworten mit passender Transaction-ID durch.**

Die Integration bringt deshalb einen eigenen Transport mit: eine
Verbindung, ein Lock, strenge Prüfung von Transaction-ID, Protokoll-ID,
Unit-ID und Länge. Dazu liest sie in Blöcken statt Register für
Register:

| | YAML, Einzelregister | diese Integration |
|---|---|---|
| Anfragen pro Minute | rund 48 | **15,4** |
| PV, Netz, Ladezustand | verschiedene Anfragen | **eine Anfrage** |
| PV-Spannungen und -Ströme | 121 s | 10 s |

Weil die berechnete Batterieleistung die Differenz aus PV und
Netzleistung ist, müssen beide aus demselben Augenblick stammen – sonst
schwankt das Ergebnis ohne physikalischen Grund.

</details>

<details>
<summary><b>Plausibilitätsfilter</b></summary>

Rohwerte außerhalb physikalisch möglicher Grenzen werden verworfen, der
letzte gute Wert bleibt stehen. Die Grenzen stehen in `const.py` unter
`VALID_RANGES`.

Die Netzleistung wird als **int16** gelesen. Die verbreitete
Community-Karte führt `0x000D` als unsigned – ein Netzbezug erschiene
dann als rund 65 000 W.

</details>

<details>
<summary><b>Eigenheiten des Geräts</b></summary>

- **Die Netzleistung pendelt.** Das ist echt: die CT-Regelung fährt der
  Hauslast nach und überschwingt. Ein Shelly am Hausanschluss zeigt
  dasselbe. Nicht wegfiltern.
- **Nach einem Firmware-Update** kann die Phasendiagnose auf 0 stehen –
  einmal über hm2mqtt neu starten.
- **`0x0011` ist der Fehlercode**, nicht der Batteriestrom. Das Register
  liefert dezimal, was das Handbuch hexadezimal notiert
  (1062 = 0x426).
- **`0x0020` / `0x0021` sind Zellspannungen**, keine Temperaturen: Wert
  mal 16 Zellen ergibt die Batteriespannung.

</details>

<details>
<summary><b>Tests</b></summary>

`python3 tests/test_integration.py` läuft ohne Home Assistant (Python
3.11 oder neuer). Ein Simulator bildet die Eigenheiten des Geräts nach:
höchstens 8 Register, Exception bei Bereichsüberschreitung, verirrte
und verspätete Antworten. Geprüft werden unter anderem:

- jede benötigte Adresse liegt in einem Leseblock
- eine verirrte Antwort verfälscht den Ladezustand nicht
- 20 gleichzeitige Anfragen bleiben getrennt
- die Energiezähler rechnen richtig und überbrücken keine Ausfälle

</details>

---

MIT-Lizenz · [Fehler melden](https://github.com/Lordodin838/marstek-jupiter-c-plus-hacs/issues)
