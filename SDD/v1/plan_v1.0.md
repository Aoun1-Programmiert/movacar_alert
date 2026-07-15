# Technischer Plan: API-Monitor & Mail-Notifier (plan_v1.0.md)

## 1. Ziel und Scope des Plans

Dieser Plan beschreibt die technische Umsetzung von `spec_v1.md` für ein headless Hintergrundprogramm zur periodischen API-Überwachung mit E-Mail-Benachrichtigung bei neuen Angeboten.

Im Scope dieses Plans:
- technische Architektur und Modulzuschnitt
- Datenmodell und Persistenzlogik
- interne und externe Schnittstellen/Contracts
- Ablaufsteuerung, Fehlerbehandlung, Logging und Konfiguration

Nicht im Scope dieses Plans:
- Task-Zerlegung/Umsetzungsaufgaben
- Quellcode-Implementierung
- fachliche Erweiterungen über `spec_v1.md` hinaus

## 2. Technische Leitentscheidungen

Festgelegt für diesen SDD-Kreis:
- **Sprache/Runtime:** Python 3.x
- **Laufmodus:** Dauerprozess (Endlosschleife + Sleep)
- **Default-Intervall:** 15 Minuten
- **Persistenz:** lokale SQLite-Datei
- **E-Mail-Format:** einfaches HTML mit klarer Hervorhebung
- **Konfiguration/Secrets:** `.env` + Umgebungsvariablen
- **Logging:** strukturiertes JSON-Logging auf stdout, optional zusätzlich Datei
- **Struktur:** schlanke modulare Aufteilung
- **Geo-Bounds DE:** feste Default-Konstante im Code, per ENV überschreibbar
- **DB-Schema-Handling:** Initialisierung beim Start via `CREATE TABLE IF NOT EXISTS`

## 3. Architekturübersicht

Vorgeschlagene Module und Verantwortlichkeiten:

1. `config`
   - lädt und validiert ENV-Konfiguration
   - liefert typed Runtime-Settings (Intervall, DB-Pfad, SMTP, API-URL, Timeouts)

2. `api_client`
   - führt HTTP-GET gegen Ziel-API aus
   - gibt Roh-JSON zurück oder signalisiert transportbezogenen Fehler

3. `parser`
   - extrahiert Angebote aus `data`
   - löst `origin`/`destination` über `included` auf
   - normalisiert Felder für interne Verarbeitung

4. `matcher` (Domain-Logik)
   - berechnet Highlight-Flag (`duration >= 2 Tage`, `origin in DE`, `destination not in DE`)
   - erzeugt Delta gegen Persistenzzustand (`new`, `existing`, `removed`)

5. `storage` (SQLite)
   - initialisiert Schema
   - liest bekannte Angebote
   - schreibt neue Angebote (nur nach erfolgreichem Mailversand)
   - bereinigt entfernte Angebote

6. `mailer`
   - rendert HTML-E-Mail (Sektion neue Angebote, Sektion bestehende Angebote)
   - versendet via SMTP

7. `loop`
   - orchestriert Polling-Zyklus inkl. Fehlerpfade und Sleep-Steuerung

## 4. Datenmodell / wichtige Entitäten

### 4.1 Persistenz (SQLite)

Tabelle `offers`:
- `id` TEXT PRIMARY KEY
- `start_date` TEXT NOT NULL
- `end_date` TEXT NOT NULL
- `origin_city` TEXT NOT NULL
- `destination_city` TEXT NOT NULL
- `free_km` INTEGER NOT NULL
- `first_seen_timestamp` TEXT NOT NULL

Hinweise:
- Datums-/Zeitwerte werden in stabil vergleichbarer Form gespeichert (ISO-8601).
- Primärschlüssel `id` verhindert doppelte Zustandsaufnahme.

### 4.2 In-Memory Domain-Objekte

- `Offer`: `id`, `start_date`, `end_date`, `free_km`, `origin(city,lat,lon)`, `destination(city,lat,lon)`
- `ClassifiedOffer`: `Offer` + `is_highlighted` + `state` (`new`/`existing`)

## 5. Schnittstellen und Contracts

### 5.1 Externe Schnittstellen

- **API (HTTP GET)**
  - Input: URL, Timeout-Konfiguration
  - Output: JSON mit `data` + `included`
  - Fehler: Netzwerk/Timeout/ungültige Antwortstruktur

- **SMTP**
  - Input: Host, Port, Nutzer, Passwort, TLS-Optionen, Sender/Empfänger
  - Output: Versand erfolgreich/fehlgeschlagen
  - Fehler: Authentifizierung, Verbindungsaufbau, Transportfehler

### 5.2 Interne Modul-Contracts

- `parser` liefert nur vollständig aufgelöste Angebote; unvollständige Datensätze werden als Parsing-Fehler signalisiert.
- `matcher` ist deterministisch: gleicher Inputzustand führt zu gleichem Delta/Highlighting.
- `storage` wird nur mit bereits validierten Daten aufgerufen.
- `mailer` erhält bereits klassifizierte Listen (`new`, `existing`) und entscheidet nicht über Fachlogik.

## 6. Steuerung des Programmablaufs / Haupt-Workflow

Pro Zyklus:

1. API abrufen (`api_client`)
2. JSON parsen und Stationen auflösen (`parser`)
3. Highlight-Kriterien bewerten (`matcher`)
4. Persistenzzustand laden (`storage`)
5. Delta berechnen (`matcher`)
6. Wenn keine neuen Angebote:
   - nur Cleanup entfernter IDs in DB
   - kein Mailversand
7. Wenn mindestens ein neues Angebot:
   - HTML-Mail erstellen und versenden (`mailer`)
   - **nur bei erfolgreichem Versand** neue IDs in DB speichern
   - entfernte IDs bereinigen
8. Sleep bis nächster Zyklus (Default 15 min)

## 7. Speicherung / Dateien / Datenbank

- SQLite-Datei lokal auf dem Rechner, Pfad über ENV konfigurierbar.
- Schema-Initialisierung beim Prozessstart.
- Keine weitere Persistenz außerhalb SQLite.
- `.env` liegt lokal und enthält Konfigurationswerte inkl. SMTP-Credentials.

## 8. Fehlerbehandlung, Logging, Konfiguration

### 8.1 Fehlerbehandlung

- API-Fehler: Zyklus wird protokolliert und regulär fortgesetzt (kein Prozessabbruch).
- SMTP-Fehler: Zyklus wird protokolliert; neue Angebote werden **nicht** als gesehen persistiert.
- Parsing-/Datenqualitätsfehler: betroffener Zyklus als Fehlerfall protokollieren; kein stilles Verschlucken.
- DB-Fehler: als kritischer technischer Fehler loggen; Prozessverhalten (weiterlaufen vs. stop) als Open Item spezifizieren.

### 8.2 Logging

- JSON-Logevents mit Level `INFO`, `WARN`, `ERROR`.
- Pflichtfelder je Event: `timestamp`, `level`, `event`, `cycle_id`, `message`.
- Wichtige Events: Zyklusstart/-ende, API-Erfolg/Fehler, Anzahl new/existing/removed, Mail-Erfolg/Fehler, DB-Write/Cleanup.
- Ausgabe standardmäßig stdout; optionale Datei aktivierbar.

### 8.3 Konfiguration (ENV)

Geplante Variablen (Namen als technische Konvention, final in Umsetzung):
- `API_URL`
- `POLL_INTERVAL_MINUTES` (Default 15)
- `SQLITE_PATH`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- `SMTP_FROM`, `SMTP_TO`
- `SMTP_USE_TLS`
- `HTTP_TIMEOUT_SECONDS`
- `DE_BBOX_MIN_LAT`, `DE_BBOX_MAX_LAT`, `DE_BBOX_MIN_LON`, `DE_BBOX_MAX_LON` (optional Overrides)
- `LOG_FILE_PATH` (optional)

Konfigurationsvalidierung erfolgt beim Start; fehlende Pflichtwerte führen zu klarer Fehlermeldung.

## 9. Technische Annahmen (Assumptions)

- API bleibt ohne zusätzliche Authentifizierung aufrufbar.
- API liefert weiterhin die benötigten Felder (`data`/`included`, IDs, Koordinaten, Datumswerte).
- SMTP-Zugangsdaten sind gültig und lokal sicher hinterlegt.
- Laptop-Standby unterbricht nur Laufzeit, nicht den persistierten Zustand.

## 10. Open Items

- Exakte SMTP-Transportparameter (STARTTLS/SSL, Port-Standard).
- Präzise HTML-Mail-Struktur (Layouttiefe, Markierungsstil für „äußerst interessant“).
- Konkrete Timeout-/Retry-Werte (API/SMTP) und Backoff-Regeln.
- Zeitzonenpolitik für Datumsvergleich (`UTC` vs. lokale Zeit).
- Verhalten bei kritischen DB-Fehlern (Fail-fast vs. kontrolliertes Weiterlaufen).
- Optionale Log-Rotation bei Datei-Logging.

## 11. Grenzen des Plans

Dieser Plan deckt nicht ab:
- Betrieb in Cloud-/Server-Infrastruktur
- UI/Bedienoberflächen
- Multi-Empfänger-Verwaltung per Oberfläche
- Erweiterte Auth-/Token-Mechanismen
- fachliche Kriterien jenseits der in `spec_v1.md` freigegebenen Regeln

