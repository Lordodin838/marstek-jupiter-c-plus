# Changelog

## 1.1.0

### New

- **Energy counters for the Energy dashboard:** *PV energy*, *Battery
  charged* and *Battery discharged* (kWh). The integration accumulates
  them itself from the 10 s power values, so Riemann integral helpers are
  no longer needed. Only freshly read values are counted; outages longer
  than 60 s are not extrapolated. The counters survive restarts.
- **Error code as a repair issue:** when the device reports an error code,
  Home Assistant shows it under *Settings → Repairs* with the plain-text
  description, and the integration fires the event
  `marstek_jupiter_error`. The issue disappears when the code returns
  to 0.
- **Release workflow:** a release is created in one step
  (*Actions → Release*); it checks the version in `manifest.json` and
  takes the release notes from this file.
- **English README** as the main page (shown by HACS), German in
  `README.de.md`. Both reorganised for the HACS view on a phone.

### Removed

- The entities *Diagnostic 0x0012*, *Diagnostic 0x0023* and
  *Status 0x1000–0x1003, 0x1009, 0x100A*. The registers are still read
  and can be inspected with `read_register` or `register_dump`. Their
  old registry entries are removed automatically on the first start.

### Upgrade notes

- Restart Home Assistant after updating.
- To keep the history of existing Riemann helpers in the Energy
  dashboard, give the new counters the helpers' entity IDs (delete the
  helper first, then rename the new entity).

---

### Deutsch

#### Neu

- **Energiezähler fürs Energie-Dashboard:** *PV Energie*, *Batterie
  geladen* und *Batterie entladen* (kWh), von der Integration selbst aus
  den 10-s-Leistungswerten aufsummiert – Riemann-Helfer sind nicht mehr
  nötig. Gezählt wird nur, was frisch gelesen wurde; Ausfälle über 60 s
  werden nicht hochgerechnet. Der Stand überlebt Neustarts.
- **Fehlercode als Reparatur-Meldung:** Meldet das Gerät einen
  Fehlercode, erscheint er mit Klartext unter *Einstellungen →
  Reparaturen*, zusätzlich feuert das Ereignis `marstek_jupiter_error`.
  Steht der Code wieder auf 0, verschwindet die Meldung.
- **Release-Workflow:** Ein Release ist ein Schritt (*Actions → Release*)
  und prüft die Version in `manifest.json`.
- **README auf Englisch** als Hauptseite, Deutsch in `README.de.md`.

#### Entfernt

- Die Entitäten *Diagnose 0x0012*, *Diagnose 0x0023* und *Status
  0x1000–0x1003, 0x1009, 0x100A*. Die alten Einträge räumt die
  Integration beim ersten Start selbst weg.

## 1.0.1

- **Fix:** entities update again. In 1.0.0 every entity only showed the
  value from when the integration started and then stayed frozen.
- **Fehlerbehebung:** Entitäten aktualisieren sich wieder. In 1.0.0
  blieben alle Werte nach dem Start stehen.

## 1.0.0

- First release: local Modbus TCP integration for the Marstek Jupiter C+
  via Elfin EW11/EE11, block reads, plausibility filter, adoption of
  existing YAML entity IDs, services `register_dump` and `read_register`.
