# Task-Liste: API-Monitor & Mail-Notifier (tasks_v1.1.md)

Ableitung aus `plan_v1.1.md` (primär) mit Validierung gegen `spec_v1.0.md` (sekundär).

## Leitplanken

- Nur Inhalte aus Plan/Spec dieses SDD-Kreises.
- Jeder Task ist programmierbar, klein und testbar.
- Tests sind pro Task verpflichtend.
- Testdaten-Fixture: `tests/example_response.json` (falls relevant).
- Error Handling wird in den jeweiligen Fach-Tasks umgesetzt (kein separater Error-Handling-Task).

---

## T-BOOT-01 — `src/`-Projektstruktur und Modulgrenzen anlegen

**Beschreibung**  
Lege die in Plan v1.1 definierte `src/`-Struktur an und setze klare Modulgrenzen (Transport vs Fachlogik vs Orchestrierung).

**Acceptance Criteria**
- [x] Verzeichnisstruktur entspricht Plan-Layout unter `src/`.
- [x] Module sind domänenscharf getrennt (`api`, `parser`, `matcher`, `storage`, `mailer`, `loop`, `config`, `models`, `logging`).
- [x] Kein Mischcode zwischen Transport- und Fachlogik-Bereichen.
- [x] Basistests prüfen, dass Importpfade/Modulstruktur konsistent auflösbar sind.

**Betroffene Dateien / Module / Pfade**
- `src/config/`
- `src/api/`
- `src/parser/`
- `src/matcher/`
- `src/storage/`
- `src/mailer/`
- `src/loop/`
- `src/models/`
- `src/logging/`
- `tests/test_project_structure.py`

**Abhängigkeiten**
- keine

**Ausführung**
- **Sequenziell** (Startpunkt)

**Referenzen**
- Plan: Abschnitt 3, 5

---

## T-ENV-01 — Python `venv` + `requirements.txt` Basis aufsetzen

**Beschreibung**  
Setze die Abhängigkeitsstrategie gemäß Plan verbindlich um (`venv` + `requirements.txt`) und dokumentiere/etabliere reproduzierbare Installation.

**Acceptance Criteria**
- [x] `requirements.txt` ist vorhanden und enthält nur benötigte Abhängigkeiten.
- [x] Projekt läuft mit Python-`venv` reproduzierbar.
- [x] Keine unnötige zusätzliche Toolchain eingeführt.
- [x] Tests/Projekt-Setup funktionieren in frischer Umgebung.

**Betroffene Dateien / Module / Pfade**
- `requirements.txt`
- optional: bestehende Setup-Hinweise (falls im Repo vorhanden)
- `tests/` (Smoke-Test für lauffähiges Setup)

**Abhängigkeiten**
- T-BOOT-01

**Ausführung**
- **Sequenziell** nach T-BOOT-01

**Referenzen**
- Plan: Abschnitt 4

---

## T-CONFIG-01 — Runtime-Settings und ENV-Validierung implementieren

**Beschreibung**  
Implementiere `src/config/settings.py` zum Laden/Validieren aller Konfigurationswerte inkl. Defaults und optionaler Overrides.

**Acceptance Criteria**
- [ ] Pflichtwerte (`API_URL`, SMTP-Basis, `SQLITE_PATH`) werden beim Start validiert.
- [ ] `POLL_INTERVAL_MINUTES` defaultet auf 15.
- [ ] BBox-Overrides sind optional; ohne Override gelten Code-Defaults.
- [ ] Settings liegen als typisierte Runtime-Konfiguration vor.
- [ ] Unit-Tests decken valide/invalid ENV-Konfiguration und Defaults ab.

**Betroffene Dateien / Module / Pfade**
- `src/config/settings.py`
- `tests/test_settings.py`

**Abhängigkeiten**
- T-ENV-01

**Ausführung**
- **Sequenziell**

**Referenzen**
- Plan: Abschnitt 2, 5 (`config`), 10.3
- Spec: Abschnitt 6, 9

---

## T-MODEL-01 — Domain-Modelle `Offer` und `ClassifiedOffer` definieren

**Beschreibung**  
Implementiere die zentralen In-Memory-Entitäten gemäß Contract für parser/matcher/mailer/storage.

**Acceptance Criteria**
- [ ] `Offer` enthält alle geforderten Felder inkl. Origin/Destination mit Geo-Daten.
- [ ] `ClassifiedOffer` erweitert um `is_highlighted` und `state`.
- [ ] Typen/Validität sind für nachgelagerte Module eindeutig.
- [ ] Unit-Tests prüfen Modellkonsistenz und erwartete Felder.

**Betroffene Dateien / Module / Pfade**
- `src/models/offer.py`
- `tests/test_models_offer.py`

**Abhängigkeiten**
- T-CONFIG-01

**Ausführung**
- **Parallelisierbar** zu T-API-01/T-DB-01 nach T-CONFIG-01

**Referenzen**
- Plan: Abschnitt 6.2, 7.2

---

## T-DB-01 — SQLite-Schema `offers` initialisieren

**Beschreibung**  
Implementiere Schema-Init (`CREATE TABLE IF NOT EXISTS`) in `sqlite_store` gemäß Plan-Schema.

**Acceptance Criteria**
- [ ] Tabelle `offers` enthält: `id`, `start_date`, `end_date`, `origin_city`, `destination_city`, `free_km`, `first_seen_timestamp`.
- [ ] Soft-Delete-Felder sind enthalten: `is_deleted` (BOOL/INTEGER, Default `0`) und `deleted_at` (TEXT, nullable, ISO-8601).
- [ ] Primärschlüssel auf `id` ist gesetzt.
- [ ] Initialisierung ist idempotent.
- [ ] Unit-Tests prüfen Schema und Idempotenz.

**Betroffene Dateien / Module / Pfade**
- `src/storage/sqlite_store.py`
- `tests/test_sqlite_schema.py`

**Abhängigkeiten**
- T-CONFIG-01

**Ausführung**
- **Parallelisierbar** zu T-API-01/T-MODEL-01

**Referenzen**
- Plan: Abschnitt 2, 6.1, 9
- Spec: Abschnitt 4 (Hinweis: Plan erweitert um `free_km`)

---

## T-DB-02 — Storage-Operationen (read/insert/cleanup) implementieren

**Beschreibung**  
Implementiere Lesen bekannter Angebote, Schreiben neuer Angebote und Soft-Delete-Markierung entfernter IDs.

**Acceptance Criteria**
- [ ] Read liefert nutzbaren Zustand für Delta-Berechnung.
- [ ] Insert schreibt nur valide Angebote in alle erforderlichen Spalten.
- [ ] Entfernte IDs werden **nicht physisch gelöscht**, sondern auf `is_deleted=1` gesetzt und mit `deleted_at` (lokale Zeit, ISO-8601) markiert.
- [ ] Falls ein soft-gelöschtes Angebot wieder in der API erscheint, wird es reaktiviert (`is_deleted=0`, `deleted_at=NULL`).
- [ ] Fehlerfälle werden explizit signalisiert (nicht still geschluckt).
- [ ] Unit-Tests decken Read/Insert/Cleanup inkl. Fehlerfälle ab.
- [ ] Bei kritischen DB-Fehlern läuft der Prozess kontrolliert weiter: Fehler loggen, aktuellen Zyklus abbrechen, nächsten Zyklus regulär starten.
- [ ] Tests validieren das Verhalten „kontrolliertes Weiterlaufen“ bei kritischen DB-Fehlern.

**Betroffene Dateien / Module / Pfade**
- `src/storage/sqlite_store.py`
- `tests/test_sqlite_store_ops.py`

**Abhängigkeiten**
- T-DB-01
- T-MODEL-01

**Ausführung**
- **Sequenziell** nach T-DB-01

**Referenzen**
- Plan: Abschnitt 5 (`storage`), 8, 10.1
- Spec: Abschnitt 4, 7

---

## T-DB-03 — Retention-Purge für Soft-Deletes (14 Tage) implementieren

**Beschreibung**  
Implementiere eine Storage-Funktion, die soft-gelöschte Angebote nach Ablauf von 14 Tagen endgültig aus der DB entfernt.

**Acceptance Criteria**
- [ ] Hard-Delete greift nur für Datensätze mit `is_deleted=1` und `deleted_at < (now - 14 Tage)`.
- [ ] Purge ist idempotent und kann pro Zyklus sicher aufgerufen werden.
- [ ] Zeitvergleich nutzt lokale Zeitbasis konsistent zur restlichen Zeitzonenentscheidung.
- [ ] Unit-Tests decken Fälle „jünger als 14 Tage“, „älter als 14 Tage“ und Grenzzeitpunkt ab.

**Betroffene Dateien / Module / Pfade**
- `src/storage/sqlite_store.py`
- `tests/test_sqlite_store_retention.py`

**Abhängigkeiten**
- T-DB-02

**Ausführung**
- **Sequenziell** nach T-DB-02

**Referenzen**
- Plan: Abschnitt 5 (`storage`), 8 (Cleanup-Schritt erweitert)
- Spec: Abschnitt 4 (Löschlogik, hier als bewusste Erweiterung via Soft-Delete)

---

## T-API-01 — API-Client für HTTP-GET inkl. Timeout/Fehlerpfade implementieren

**Beschreibung**  
Implementiere `src/api/api_client.py` für API-Abruf mit konfigurierbarem Timeout und klaren Fehlersignalen.

**Acceptance Criteria**
- [ ] API-GET nutzt URL + Timeout aus Settings.
- [ ] Erfolgsfall liefert Roh-JSON.
- [ ] Netzwerk-/Timeout-/Strukturfehler werden explizit signalisiert.
- [ ] Unit-Tests decken Erfolgs- und Fehlerpfade ab.
- [ ] Timeout-/Retry-/Backoff sind verbindlich umgesetzt: **15s Timeout, 3 Retries, exponentieller Backoff 1s/2s/4s**.
- [ ] Tests validieren die konfigurierte Retry-/Backoff-Strategie.

**Betroffene Dateien / Module / Pfade**
- `src/api/api_client.py`
- `tests/test_api_client.py`

**Abhängigkeiten**
- T-CONFIG-01

**Ausführung**
- **Parallelisierbar** zu T-DB-02

**Referenzen**
- Plan: Abschnitt 5 (`api_client`), 7.1, 10.1
- Spec: Abschnitt 2, 7

---

## T-PARSER-01 — Angebots-Parsing und Stationen-Auflösung implementieren

**Beschreibung**  
Implementiere Parser, der `data` extrahiert, `origin`/`destination` über `included` auflöst und vollständige `Offer`-Objekte liefert.

**Acceptance Criteria**
- [ ] `id`, `start_date`, `end_date`, `free_km`, Origin/Destination werden vollständig aufgelöst.
- [ ] Unvollständige Datensätze werden als Parsing-Fehler signalisiert.
- [ ] Parser liefert ausschließlich valide, vollständige Offers.
- [ ] Tests nutzen `tests/example_response.json` für den Hauptfall.
- [ ] Zusätzliche Tests prüfen fehlende Beziehungen/Pflichtfelder.

**Betroffene Dateien / Module / Pfade**
- `src/parser/offer_parser.py`
- `tests/test_offer_parser.py`
- `tests/example_response.json` (read-only Fixture)

**Abhängigkeiten**
- T-API-01
- T-MODEL-01

**Ausführung**
- **Sequenziell** nach T-API-01

**Referenzen**
- Plan: Abschnitt 5 (`parser`), 7.2, 8
- Spec: Abschnitt 2, 4

---

## T-MATCH-01 — Geo-Regeln (DE-Bounding-Box) kapseln

**Beschreibung**  
Implementiere dedizierte Geo-Regeln in `geo_rules.py` zur Prüfung „in DE“ / „außerhalb DE“ auf Basis Koordinaten.

**Acceptance Criteria**
- [ ] DE-BBox-Defaults werden korrekt angewendet.
- [ ] ENV-Overrides werden berücksichtigt.
- [ ] Grenz- und Randfälle sind determiniert getestet.
- [ ] Unit-Tests decken positive/negative und Grenzkoordinaten ab.

**Betroffene Dateien / Module / Pfade**
- `src/matcher/geo_rules.py`
- `tests/test_geo_rules.py`

**Abhängigkeiten**
- T-CONFIG-01
- T-MODEL-01

**Ausführung**
- **Parallelisierbar** zu T-DB-02/T-PARSER-01 (nach T-MODEL-01)

**Referenzen**
- Plan: Abschnitt 2, 5 (`matcher`), 10.3
- Spec: Abschnitt 2 (Highlight), 6

---

## T-MATCH-02 — Highlight- und Delta-Logik implementieren

**Beschreibung**  
Implementiere in `offer_matcher.py` die Highlight-Regel und die Delta-Klassifikation (`new`, `existing`, `removed`).

**Acceptance Criteria**
- [ ] Highlight-Regel: Dauer ≥ 2 Tage UND Origin in DE UND Destination außerhalb DE.
- [ ] Delta korrekt für alle Zustandsübergänge.
- [ ] Deterministisches Verhalten bei identischem Input.
- [ ] Unit-Tests decken Highlight- und Delta-Fälle vollständig ab.

**Betroffene Dateien / Module / Pfade**
- `src/matcher/offer_matcher.py`
- `tests/test_offer_matcher.py`

**Abhängigkeiten**
- T-PARSER-01
- T-MATCH-01
- T-DB-02

**Ausführung**
- **Sequenziell**

**Referenzen**
- Plan: Abschnitt 5 (`matcher`), 7.2, 8
- Spec: Abschnitt 2, 4, 5

---

## T-MAIL-01 — HTML-Template-Rendering implementieren

**Beschreibung**  
Implementiere Mail-Templates mit Sektionen „neu“ und „bestehend“ sowie klarer visueller Highlight-Markierung.

**Acceptance Criteria**
- [ ] HTML enthält beide Sektionen in stabiler Struktur.
- [ ] Highlight-Angebote sind deutlich hervorgehoben.
- [ ] Renderer verarbeitet bereits klassifizierte Daten, ohne Fachentscheidungen zu treffen.
- [ ] Tests validieren Struktur, Sektionen und Highlight-Output.
- [ ] **Open-Item-Vermerk:** Finale Mail-Struktur/Markierungsstil wird in diesem Task festgelegt und als Test-Oracle abgesichert.

**Betroffene Dateien / Module / Pfade**
- `src/mailer/templates.py`
- `tests/test_mail_templates.py`

**Abhängigkeiten**
- T-MATCH-02

**Ausführung**
- **Parallelisierbar** zu T-MAIL-02

**Referenzen**
- Plan: Abschnitt 5 (`mailer`), 12 (HTML Open Item)
- Spec: Abschnitt 2

---

## T-MAIL-02 — SMTP-Versand implementieren

**Beschreibung**  
Implementiere SMTP-Transport in `smtp_mailer.py` mit klaren Erfolgs-/Fehlersignalen und Konfigurationsbindung.

**Acceptance Criteria**
- [ ] SMTP-Parameter werden vollständig aus Settings genutzt.
- [ ] Versand-Erfolg und Versand-Fehler sind eindeutig unterscheidbar.
- [ ] Fehler werden nicht als Erfolg maskiert.
- [ ] Unit-Tests decken Erfolg, Auth-/Connect-/Transportfehler ab.
- [ ] **Open-Item-Vermerk:** Exakte SMTP-Transportparameter (STARTTLS/SSL/Port) werden in diesem Task final entschieden und dokumentiert.

**Betroffene Dateien / Module / Pfade**
- `src/mailer/smtp_mailer.py`
- `tests/test_smtp_mailer.py`

**Abhängigkeiten**
- T-CONFIG-01

**Ausführung**
- **Parallelisierbar** zu T-MAIL-01

**Referenzen**
- Plan: Abschnitt 5 (`mailer`), 7.1, 10.1, 12
- Spec: Abschnitt 2, 7

---

## T-LOG-01 — JSON-Logger mit Event-Contract implementieren

**Beschreibung**  
Implementiere strukturiertes JSON-Logging inkl. Pflichtfelder und Event-Typen gemäß Plan.

**Acceptance Criteria**
- [ ] Pflichtfelder: `timestamp`, `level`, `event`, `cycle_id`, `message`.
- [ ] Level `INFO/WARN/ERROR` konsistent.
- [ ] Wichtige Events abdeckbar (Cycle Start/Ende, API, Delta, Mail, DB).
- [ ] Logging erfolgt primär in eine Datei.
- [ ] Log-Rotation ist implementiert mit **10 MB pro Datei** und **5 Backups**.
- [ ] Tests validieren Feldschema und Event-Konsistenz.
- [ ] Tests validieren Datei-Logging inkl. Rotation.

**Betroffene Dateien / Module / Pfade**
- `src/logging/logger.py`
- `tests/test_logger_contract.py`

**Abhängigkeiten**
- T-CONFIG-01

**Ausführung**
- **Parallelisierbar** zu API/DB/Mail/Matcher-Tasks

**Referenzen**
- Plan: Abschnitt 10.2, 10.3
- Spec: Abschnitt 8

---

## T-LOOP-01 — Polling-Orchestrierung in `poll_loop.py` implementieren

**Beschreibung**  
Implementiere den vollständigen Zyklusfluss inkl. Branching, Persistenzregel und Sleep-Steuerung.

**Acceptance Criteria**
- [ ] Reihenfolge entspricht Plan-Workflow.
- [ ] Kein Mailversand bei `new == 0`; Soft-Delete-Markierung entfernter IDs + Retention-Purge werden dennoch ausgeführt.
- [ ] Bei `new > 0`: erst Mailversand, dann Persistenz neuer IDs.
- [ ] Bei SMTP-Fehler: keine Persistenz neuer IDs.
- [ ] API-/Parsing-Fehler führen zu Logging + Fortsetzung nächster Zyklen.
- [ ] Datumsvergleiche folgen der festgelegten lokalen Zeitzone (nicht UTC).
- [ ] Tests decken zentrale Zweige und Fehlerpfade ab.

**Betroffene Dateien / Module / Pfade**
- `src/loop/poll_loop.py`
- `tests/test_poll_loop.py`

**Abhängigkeiten**
- T-DB-02
- T-DB-03
- T-API-01
- T-PARSER-01
- T-MATCH-02
- T-MAIL-01
- T-MAIL-02
- T-LOG-01

**Ausführung**
- **Sequenziell** nach Kernmodulen

**Referenzen**
- Plan: Abschnitt 5 (`loop`), 8, 10.1
- Spec: Abschnitt 5, 7

---

## T-ENTRY-01 — Programm-Entry und Startablauf integrieren

**Beschreibung**  
Implementiere den Startpunkt, der Konfiguration lädt, Storage initialisiert und die Poll-Loop kontrolliert startet.

**Acceptance Criteria**
- [ ] Startpfad initialisiert Settings und DB-Schema vor erster Polling-Runde.
- [ ] Fehler bei Startvalidierung werden klar ausgegeben.
- [ ] Entry bleibt schlank und delegiert Fachlogik an Module.
- [ ] Tests prüfen Startverhalten (Happy Path + Config-Fehler).

**Betroffene Dateien / Module / Pfade**
- `src/main.py` (oder äquivalenter Einstiegspunkt)
- `tests/test_main_entry.py`

**Abhängigkeiten**
- T-CONFIG-01
- T-DB-01
- T-LOOP-01

**Ausführung**
- **Sequenziell**

**Referenzen**
- Plan: Abschnitt 3, 8, 9, 10.3
- Spec: Abschnitt 5

---

## T-FLOW-01 — End-to-End-Ablaufkonsistenz absichern

**Beschreibung**  
Erstelle Integrationsszenarien, die die Kern-Garantien des Systems Ende-zu-Ende gegen den spezifizierten Ablauf absichern.

**Acceptance Criteria**
- [ ] Neues Angebot: genau ein Mailversand, danach DB-Persistenz.
- [ ] Bereits bekanntes Angebot: keine „neu“-Benachrichtigung.
- [ ] Entfernte IDs: werden zunächst soft-gelöscht (`is_deleted=1`, `deleted_at` gesetzt).
- [ ] Soft-gelöschte IDs werden nach >14 Tagen endgültig aus DB entfernt.
- [ ] SMTP-Fehler: neue IDs bleiben unpersistiert.
- [ ] Tests basieren auf `tests/example_response.json` (+ gezielte Variationen).

**Betroffene Dateien / Module / Pfade**
- `tests/test_end_to_end_flow.py`
- `tests/example_response.json` (read-only Fixture)

**Abhängigkeiten**
- T-ENTRY-01

**Ausführung**
- **Sequenziell** als Abschluss

**Referenzen**
- Plan: Abschnitt 8, 10.1
- Spec: Abschnitt 4, 5, 7, 8

---

## Open Items / mögliche Konflikte

### Open Items (Status nach Abstimmung)
1. **SMTP-Transportparameter:** wird in **T-MAIL-02** final festgelegt.
2. **Mail-Struktur/Highlight-Stil:** wird in **T-MAIL-01** final festgelegt.
3. **Timeout-/Retry-/Backoff-Werte:** **entschieden = 15s, 3 Retries, exponentiell 1s/2s/4s** (in **T-API-01** umzusetzen).
4. **Zeitzonenpolitik:** **entschieden = lokal**.
5. **DB-Fehlerstrategie (kritisch):** **entschieden = kontrolliertes Weiterlaufen** (in **T-DB-02/T-LOOP-01** umzusetzen).
6. **Datei-Logging mit Rotation:** **entschieden = 10 MB, 5 Backups** (in **T-LOG-01** umzusetzen).

### Mögliche Spec/Plan-Spannung
- **DB-Schema:** `plan_v1.1` enthält zusätzlich `free_km`; `spec_v1.0` nennt ein minimales Schema ohne `free_km`.  
  Bewertung: **kein direkter Widerspruch**, aber als bewusste Plan-Erweiterung kenntlich.
- **Löschsemantik:** `spec_v1.0`/`plan_v1.1` beschreiben direkte Bereinigung entfernter IDs; in `tasks_v1.1` wurde dies bewusst zu Soft-Delete + 14-Tage-Retention erweitert.  
  Bewertung: **gezielte fachliche Erweiterung**, in Implementierung konsistent umzusetzen.