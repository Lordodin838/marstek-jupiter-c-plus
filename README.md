# Marstek Jupiter C+ für Home Assistant

Lokale Modbus-TCP-Integration für den **Marstek Jupiter C+** hinter einem
RS485-WLAN-Umsetzer (Elfin EW11 / EE11). Einrichtung über die Oberfläche,
keine YAML-Konfiguration, keine Cloud, keine zusätzlichen Python-Pakete.

Die Registerkarte ist an einem realen Gerät erarbeitet worden
(Firmware 142.37.213.110, Gerätetyp 0 = Jupiter C 800 W). Wo sie von der
verbreiteten Community-Karte abweicht, steht der Grund im Quelltext.

---

## Warum nicht einfach die Modbus-Integration von Home Assistant

Der Elfin-Umsetzer hat zwei Eigenheiten, an denen eine gewöhnliche
Modbus-Konfiguration scheitert:

1. **Er bearbeitet immer nur eine Anfrage.** Kommen zwei kurz
   hintereinander, ordnet er Antworten der falschen Anfrage zu. Sichtbar
   wird das als *richtiger Wert im falschen Sensor* — ein Ladezustand von
   3308 %, weil die Antwort der Zellspannungs-Abfrage im SoC-Sensor
   landete.
2. **Er reicht fremde Antworten mit passender Transaction-ID durch.**

Diese Integration bringt deshalb einen eigenen kleinen Modbus-Transport
mit: eine Verbindung, ein Lock, strenge Prüfung von Transaction-ID,
Protokoll-ID, Unit-ID und Antwortlänge. Was nicht exakt zur eigenen
Anfrage passt, wird verworfen statt übernommen.

Dazu kommt die Blocklesung. Statt 16 Einzelanfragen für
`0x0001`–`0x0010` liest die Integration zwei Blöcke zu je 8 Registern:

| | bisher (YAML, Einzelregister) | diese Integration |
|---|---|---|
| Anfragen pro Minute | rund 48 | **15,4** |
| PV-Leistungen, Netzleistung, SoC | 10 s, aber aus verschiedenen Anfragen | 10 s, **aus derselben Anfrage** |
| PV-Spannungen und -Ströme | 121 s | 10 s (kommen gratis mit) |
| Zellspannung max/min | 61 s und 67 s, 6 s versetzt | gemeinsam, kein Versatz |

Dass die regelungsrelevanten Werte aus **einer** Anfrage stammen, ist
kein Schönheitsfehler-Fix: die berechnete Batterieleistung ist die
Differenz aus PV-Summe und Netzleistung. Stammen die Summanden aus
verschiedenen Augenblicken, schwankt das Ergebnis ohne physikalischen
Grund.

## Entitäten

**Messwerte** — PV1–4 Spannung/Strom/Leistung, PV-Gesamtleistung,
Netzleistung, Batteriespannung, Ladezustand, berechnete Batterieleistung,
Temperatur.

**Energiezähler** — Tages- und Monatsertrag, Tages- und
Monatseinspeisung. Direkt für das Energie-Dashboard geeignet.

**Batterie** — Zellspannung max und min, Zelldrift in mV. Unter 50 mV ist
ein gesunder Pack, über 100 mV läuft eine Zelle davon — ein früher
Hinweis auf Alterung, lange bevor die Kapazität sichtbar nachlässt.

**Diagnose** — Fehlercode und Fehlercode im Klartext (Tabelle aus dem
Handbuch, Abschnitt 5.1), EMS-/INV-/MPPT-/BMS-/Display-Version,
Gerätetyp, MAC-Adresse, Firmware des Kommunikationsmoduls, Statusflags
PV1–4 und Wechselrichter.

Nicht dokumentierte Register (`0x0012`, `0x0023`, die übrigen
Statusflags) sind als abgeschaltete Diagnose-Entitäten dabei — sie kommen
im Block ohnehin mit und kosten nichts.

### Was das Gerät nicht liefert

Damit niemand weiter danach sucht:

* **Kein Register für die DC-Batterieleistung.** `0x000E` wurde dafür
  getestet und ist es nicht — der Wert stand konstant auf 300, während PV
  zwischen 472 und 493 W lief. Die Integration berechnet die
  Batterieleistung aus der Bilanz.
* **Kein Register für die Entladetiefe oder SoC-Grenze.** Die läuft
  ausschließlich über hm2mqtt.
* **Keine Einzelspannungen der 16 Zellen**, nur Maximum und Minimum.
* `0x4000`–`0x43FF` ist write-only und liefert lesend nichts. Diese
  Integration schreibt nicht ins Gerät.

## Plausibilitätsfilter

Zweites Netz unter der Transaction-ID-Prüfung: Rohwerte außerhalb
physikalisch möglicher Grenzen werden verworfen, der letzte gute Wert
bleibt stehen. Ein Ladezustand von 3308 kommt gar nicht erst in den
Verlauf. Die Grenzen stehen in `const.py` unter `VALID_RANGES`.

Die Netzleistung wird als **int16** gelesen. Die verbreitete
Community-Registerkarte führt `0x000D` als unsigned — als uint16 erschiene
ein Netzbezug als rund 65 000 W und würde jede Hausverbrauchs-Rechnung
zerlegen.

## Installation

### Über HACS

1. HACS → Dreipunktmenü → *Benutzerdefinierte Repositories*
2. Diese Repository-URL eintragen, Kategorie *Integration*
3. *Marstek Jupiter C+* herunterladen
4. Home Assistant neu starten
5. *Einstellungen → Geräte & Dienste → Integration hinzufügen* →
   *Marstek Jupiter C+*

### Von Hand

Den Ordner `custom_components/marstek_jupiter` nach
`config/custom_components/` kopieren und neu starten.

### Einstellungen des Umsetzers

Der Elfin muss stehen auf: 115200 Bd, 8/None/1, Protokoll **Modbus**,
Flow Control **Half Duplex**, CLI **Disabled**, **TCP Server**, Port 502,
Route UART. Und: es darf **kein zweites Programm** auf dem Umsetzer
hängen — er verträgt nur eine Verbindung.

## Umstieg von einer bestehenden YAML-Lösung

Die Integration kann die Entity-IDs einer früheren Modbus- und
Template-Konfiguration übernehmen. Verlauf, Langzeitstatistik,
Dashboards, Helfer und Automationen laufen dann ohne Nacharbeit weiter —
Verlauf und Statistik hängen an der Entity-ID, nicht an der unique_id.

**Die Reihenfolge ist entscheidend:**

1. Altes Paket deaktivieren — Datei umbenennen, zum Beispiel
   `jupiter_c_plus_modbus.yaml` → `jupiter_c_plus_modbus.yaml.aus`.
   Die zugehörigen Template-Sensoren (PV-Gesamtleistung, berechnete
   Batterieleistung, Zellspannungs-Differenz, Fehlercode Klartext,
   gefilterte Temperatur, Gerätetyp Klartext) mit entfernen.
2. **Home Assistant neu starten.** Erst jetzt sind die alten Entity-IDs
   frei.
3. Integration hinzufügen, Haken bei *Bisherige Entity-IDs übernehmen*
   stehen lassen.

Wird das alte Paket nicht vorher entfernt, schreibt die Integration eine
Warnung ins Protokoll und übernimmt nichts — die neuen Entitäten bekommen
dann IDs mit Anhängsel `_2`. Das lässt sich nur durch den sauberen Weg
beheben: Integration entfernen, Paket entfernen, neu starten, Integration
neu hinzufügen.

Übernommen werden diese unique_ids:

| bisher (Plattform) | wird zu |
|---|---|
| `jupiter_modbus_pv1..4_voltage/current/power` (modbus) | PV1–4 Spannung/Strom/Leistung |
| `jupiter_modbus_grid_power`, `_battery_voltage`, `_battery_soc` (modbus) | Netzleistung, Batteriespannung, Ladezustand |
| `jupiter_modbus_daily/monthly_generation/grid` (modbus) | Energiezähler |
| `jupiter_modbus_cell_voltage_max/min` (modbus) | Zellspannungen |
| `jupiter_modbus_*_version`, `_device_id`, `_device_type`, `_mac`, `_comm_version` (modbus) | Diagnose |
| `jupiter_diag_0011/0012/0023` (modbus) | Fehlercode, Diagnose |
| `jupiter_modbus_pv1..4_status`, `jupiter_modbus_inv_status` (modbus) | Statusflags |
| `jupiter_modbus_total_pv_power` (template) | PV-Gesamtleistung |
| `jupiter_battery_power_calculated` (template) | Batterieleistung berechnet |
| `jupiter_cell_voltage_delta` (template) | Zellspannungs-Differenz |
| `jupiter_error_code_text` (template) | Fehlercode Klartext |
| `jupiter_temperature_filtered` (template) | Temperatur |
| `jupiter_modbus_device_type_text` (template) | Gerätetyp |

Die angezeigten Namen ändern sich (aus *Jupiter Modbus PV1 Leistung* wird
*Marstek Jupiter C+ PV1 Leistung*), die IDs nicht.

## Dienste

### `marstek_jupiter.register_dump`

Legt einen vollständigen Abzug des lesbaren Registerraums an — vor und
nach einem Firmware-Update laufen lassen und vergleichen. Marstek
veröffentlicht keine Changelogs, und in der Venus-Reihe haben sich
Registeradressen zwischen Generationen nachweislich geändert.

```yaml
action: marstek_jupiter.register_dump
data:
  label: vor-update
  sweep: false
```

Ergebnis als `.json` und `.txt` in `config/marstek_jupiter/`. Der Abzug
läuft über **dieselbe Verbindung** wie die laufende Abfrage — anders als
ein externes Skript kann er sich mit ihr nicht überschneiden. Genau
daran sind frühere Scan-Versuche gescheitert: der Umsetzer reichte
fremde Antworten durch, und 49 Adressen „antworteten", die es gar nicht
gibt.

Jeder Wert wird dreimal gelesen; übernommen wird nur, was in der Mehrheit
der Durchläufe gleich war. Alles andere steht mit `NEIN` in der
Textdatei.

`sweep: true` tastet zusätzlich den gesamten Adressraum ab (zwei
Stichproben je 256er-Seite). **Ehrliche Grenze:** das findet Blöcke,
keine Einzelgänger. Ein gültiges Register zwischen toten Nachbarn — wie
`0x002A` — lässt jede 8er-Stichprobe scheitern. Wer so etwas sucht, muss
den Bereich in `SCAN_RANGES` aufnehmen, dort wird halbiert.

### `marstek_jupiter.read_register`

Einzelabfrage mit Antwort, für die Registersuche von Hand:

```yaml
action: marstek_jupiter.read_register
data:
  address: 42
  count: 1
  data_type: uint16
response_variable: ergebnis
```

## Abfragetakt ändern

*Einstellungen → Geräte & Dienste → Marstek Jupiter C+ → Konfigurieren.*

Die Faustregel für diese Anlage: **lieber wenige Sensoren langsam als
viele schnell.** Und die Zeitüberschreitung nicht unter 5 Sekunden
setzen — gibt Home Assistant zu früh auf, trifft die Antwort trotzdem ein
und wird der nächsten Anfrage zugeordnet. Genau das war die Ursache der
vertauschten Werte.

Optional lässt sich ein MQTT-Fehlersensor als zweite Quelle hinterlegen.
Vorrang hat dann das Modbus-Register (lokal, live); steht es auf 0, wird
der MQTT-Wert genommen — er hält einen Code länger, ein sehr kurzer
Fehler kann im Register zwischen zwei Abfragen durchrutschen.

## Getestet

`python3 tests/test_integration.py` läuft ohne Home Assistant: ein
Simulator bildet die Eigenheiten des Geräts nach (höchstens 8 Register,
Exception bei Bereichsüberschreitung, verirrte Antworten mit fremder
Transaction-ID, verspätete Antworten nach dem Timeout), und die
Sensorwerte werden gegen echte Messwerte der Anlage geprüft.

137 Prüfungen, darunter:

* jede Adresse, die eine Entität braucht, liegt in einem Leseblock
* kein Block überschreitet 8 Register oder die Bereichsgrenzen
* eine verirrte Antwort verfälscht den Ladezustand nicht
* 20 gleichzeitige Anfragen bleiben getrennt
* `1062` wird als `0x426` gedeutet — der Fall vom 15.09.2026

## Bekannte Eigenheiten des Geräts

**Die Netzleistung pendelt.** Das ist echt und kein Modbus-Artefakt:
ein Shelly am Hausanschluss zeigt auf derselben Phase im 5-Sekunden-Takt
dasselbe Zappeln. Es ist die CT-Regelung des Jupiter, die der Hauslast
nachfährt, überschwingt und korrigiert. Im Mittel regelt es sauber. Nicht
wegfiltern wollen.

**Nach einem Firmware-Update** kann die Phasendiagnose auf 0 stehen. Ein
Lauf über den entsprechenden Knopf in hm2mqtt stellt sie wieder her.

**`0x0011` ist der Fehlercode**, nicht der Batteriestrom. Das Handbuch
notiert die Codes hexadezimal, das Register liefert sie dezimal
(1062 = 0x426). Belegt durch vier von vier übereinstimmenden Abfragen
gegen die MQTT-Meldungen.

**`0x0020` und `0x0021` sind die Zellspannungen**, nicht zwei
Systemtemperaturen. Beleg: Wert mal 16 Zellen ergibt die Batteriespannung
aus `0x000F` (3383 → 54,1 V bei gemessenen 54,0 V). Zwei Register, die
auf 0,003 identisch sind und dem Ladezustand folgen, sind keine zwei
Systemtemperaturen.

## Lizenz

MIT
