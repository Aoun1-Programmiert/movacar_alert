# Task-Liste: API-Monitor & Mail-Notifier (tasks_v1.0.md)

Ableitung aus `plan_v1.0.md` (primär) mit Validierung gegen `spec_v1.0.md` (sekundär).

## Leitplanken für diese Task-Liste

- Nur Inhalte aus Plan/Spec dieses SDD-Kreises.
- Jeder Task ist klein, programmierbar und testbar.
- Tests sind pro Task verpflichtend.
- Als Testdatenquelle wird `tests/example_response.json` verwendet (vom Nutzer freigegeben).

---

## T-SETUP-01 — Runtime-Konfiguration und ENV-Validierung implementieren

**Beschreibung**  
Implementiere ein `config`-Modul, das `.env`/Umgebungsvariablen lädt, Pflichtwerte validiert, Defaults setzt und typsichere Runtime-Settings bereitstellt.

**Acceptance Criteria**
- [ ] Pflichtvariablen werden beim Start geprüft und bei Fehlen mit klarer Fehlermeldung abgelehnt.
- [ ] `POLL_INTERVAL_MINUTES` nutzt Default `15`, wenn nicht gesetzt.
- [ ] Optionale DE-BBOX-Overrides werden korrekt gelesen; ohne Override greifen feste Code-Defaults.
- [ ] SMTP/HTTP/SQLite/Logging-Settings sind als klarer Settings-Datentyp verfügbar.
- [ ] Unit-Tests decken valide Konfiguration, fehlende Pflichtfelder und Default-Verhalten ab.

**Betroffene Dateien / Module / Pfade**
- `movacar_alert/config.py`
- `tests/test_config.py`

**Abhängigkeiten**
- keine

**Ausführung**
- **Sequenziell** (Startpunkt)

**Referenzen**
- Plan: Abschnitt 2, 3 (`config`), 8.3
- Spec: Abschnitt 6, 9

---

## T-DB-01 — SQLite-Schema `offers` initialisieren

**Beschreibung**  
Implementiere Schema-Initialisierung beim Start via `CREATE TABLE IF NOT EXISTS` für die Tabelle `offers` gemäß Plan.

**Acceptance Criteria**
- [ ] Tabelle `offers` entspricht exakt dem geplanten Schema inkl. Primärschlüssel `id`.
- [ ] Initialisierung ist idempotent (mehrfacher Aufruf ohne Fehler).
- [ ] Datums-/Zeitfelder sind auf ISO-8601-kompatible Speicherung ausgelegt (Textformat).
- [ ] Unit-Tests verifizieren Schema-Erstellung und Idempotenz.

**Betroffene Dateien / Module / Pfade**
- `movacar_alert/storage.py`
- `tests/test_storage_schema.py`

**Abhängigkeiten**
- T-SETUP-01

**Ausführung**
- **Sequenziell** nach T-SETUP-01

**Referenzen**
- Plan: Abschnitt 2 (DB-Schema-Handling), 4.1, 7
- Spec: Abschnitt 4 (SQLite-Datenbankstruktur)

---

## T-DB-02 — Storage-Operationen (read/insert/cleanup) implementieren

**Beschreibung**  
Implementiere Lese-, Insert- und Cleanup-Operationen für Offer-State inkl. definierter Fehlerbehandlung auf Storage-Ebene.

**Acceptance Criteria**
- [ ] Laden bekannter Angebote liefert eine intern weiterverwendbare Struktur (z. B. Map/Dict nach `id`).
- [ ] Insert neuer Angebote schreibt alle geplanten Felder korrekt.
- [ ] Cleanup entfernt IDs, die nicht mehr in der aktuellen API-Menge enthalten sind.
- [ ] Fehlerfälle werden nicht still verschluckt, sondern als Fehler signalisiert/loggbar gemacht.
- [ ] Unit-Tests decken Read/Insert/Cleanup sowie typische Fehlerfälle ab.

**Betroffene Dateien / Module / Pfade**
- `movacar_alert/storage.py`
- `tests/test_storage_ops.py`

**Abhängigkeiten**
- T-DB-01

**Ausführung**
- **Parallelisierbar** zu T-API-01 (nach T-SETUP-01/T-DB-01)

**Referenzen**
- Plan: Abschnitt 3 (`storage`), 4.1, 6, 8.1
- Spec: Abschnitt 4 (logischer Ablauf), 7

---

## T-API-01 — API-Client (GET, Timeout, Response-Validierung) implementieren

**Beschreibung**  
Implementiere den HTTP-Client für API-GET inkl. Timeout-Konfiguration und klarer Signalisierung von Transport-/Strukturfehlern.

**Acceptance Criteria**
- [ ] API-GET nutzt URL und Timeout aus Konfiguration.
- [ ] Erfolgsfall liefert Roh-JSON als Input für den Parser.
- [ ] Netzwerk-/Timeout-Fehler werden explizit signalisiert.
- [ ] Ungültige Antwortstruktur wird als Fehlerfall signalisiert.
- [ ] Unit-Tests decken Erfolgsfall, Timeout, Transportfehler und ungültige Struktur ab.

**Betroffene Dateien / Module / Pfade**
- `movacar_alert/api_client.py`
- `tests/test_api_client.py`

**Abhängigkeiten**
- T-SETUP-01

**Ausführung**
- **Parallelisierbar** zu T-DB-02

**Referenzen**
- Plan: Abschnitt 3 (`api_client`), 5.1, 6, 8.1
- Spec: Abschnitt 2, 7

---

## T-PARSE-01 — Parser für `data`/`included` und Offer-Auflösung implementieren

**Beschreibung**  
Implementiere Parsing der API-Antwort: Angebote aus `data` extrahieren, `origin`/`destination` über `included` auflösen und in vollständige Domain-Objekte normalisieren.

**Acceptance Criteria**
- [ ] Für jedes Angebot werden `id`, `start_date`, `end_date`, `free_km`, Origin- und Destination-Daten vollständig aufgelöst.
- [ ] Unvollständige Datensätze werden als Parsing-Fehler signalisiert (kein stilles Überspringen).
- [ ] Parser-Ausgabe entspricht dem internen Offer-Contract aus dem Plan.
- [ ] Tests nutzen `tests/example_response.json` für den Erfolgsfall.
- [ ] Zusätzliche Tests decken fehlende `included`-Referenzen und Pflichtfeld-Lücken ab.

**Betroffene Dateien / Module / Pfade**
- `movacar_alert/parser.py`
- `tests/test_parser.py`
- `tests/example_response.json` (nur als Fixture/Read-only)

**Abhängigkeiten**
- T-API-01

**Ausführung**
- **Sequenziell** nach T-API-01

**Referenzen**
- Plan: Abschnitt 3 (`parser`), 4.2, 5.2, 6, 8.1
- Spec: Abschnitt 2, 4

---

## T-DOMAIN-01 — Highlight-Logik (Dauer + DE/Non-DE via BBox) implementieren

**Beschreibung**  
Implementiere Domain-Regel „äußerst interessant“: `duration >= 2 Tage` UND `origin in DE` UND `destination außerhalb DE`.

**Acceptance Criteria**
- [ ] Dauerprüfung basiert auf `start_date`/`end_date` gemäß definierter Zeitlogik.
- [ ] Geoprüfung nutzt DE-Bounding-Box (Defaults + ggf. ENV-Override aus Config).
- [ ] Ergebnis enthält pro Angebot ein deterministisches `is_highlighted`.
- [ ] Unit-Tests decken positive/negative Grenzfälle für Dauer und Geo-Regeln ab.

**Betroffene Dateien / Module / Pfade**
- `movacar_alert/matcher.py`
- `tests/test_matcher_highlight.py`

**Abhängigkeiten**
- T-PARSE-01
- T-SETUP-01

**Ausführung**
- **Sequenziell** nach T-PARSE-01

**Referenzen**
- Plan: Abschnitt 3 (`matcher`), 6, 8.3, 10 (Zeitzonen-Open-Item)
- Spec: Abschnitt 2 (Highlight-Logik), 6

---

## T-DOMAIN-02 — Delta-Logik (`new`/`existing`/`removed`) implementieren

**Beschreibung**  
Implementiere deterministische Zustandsklassifikation gegen Persistenzzustand (`new`, `existing`, `removed`) für den Polling-Zyklus.

**Acceptance Criteria**
- [ ] Angebote werden korrekt als `new` bzw. `existing` klassifiziert.
- [ ] Entfernte IDs werden korrekt als `removed` ausgewiesen.
- [ ] Klassifikation ist deterministisch bei identischem Inputzustand.
- [ ] Unit-Tests decken vollständige Delta-Szenarien inkl. Randfälle ab.

**Betroffene Dateien / Module / Pfade**
- `movacar_alert/matcher.py`
- `tests/test_matcher_delta.py`

**Abhängigkeiten**
- T-DOMAIN-01
- T-DB-02

**Ausführung**
- **Sequenziell** nach T-DOMAIN-01 und T-DB-02

**Referenzen**
- Plan: Abschnitt 3 (`matcher`), 5.2, 6
- Spec: Abschnitt 4 (logischer Ablauf der Erkennung)

---

## T-MAIL-01 — HTML-Mail-Rendering (Sektionen + Highlight) implementieren

**Beschreibung**  
Implementiere Mail-Renderer für HTML mit zwei Sektionen: neue Angebote und bestehende Angebote; Highlight-Angebote werden visuell klar markiert.

**Acceptance Criteria**
- [ ] HTML enthält Sektion „Neue Angebote“ und Sektion „Bestehende Angebote“.
- [ ] Highlight-Angebote sind im HTML deutlich markiert.
- [ ] Renderer trifft keine Fachentscheidung (erhält bereits klassifizierte Listen).
- [ ] Tests prüfen Struktur, Sektionen und Highlight-Ausgabe (Snapshot/strukturell).

**Betroffene Dateien / Module / Pfade**
- `movacar_alert/mailer.py`
- `tests/test_mailer_render.py`

**Abhängigkeiten**
- T-DOMAIN-01

**Ausführung**
- **Parallelisierbar** zu T-MAIL-02

**Referenzen**
- Plan: Abschnitt 3 (`mailer`), 5.2, 10 (HTML-Open-Item)
- Spec: Abschnitt 2 (E-Mail-Umfang + Highlight)

---

## T-MAIL-02 — SMTP-Versandmodul implementieren

**Beschreibung**  
Implementiere SMTP-Versand inklusive konfigurierbarer Transportparameter und klarer Fehlerbehandlung.

**Acceptance Criteria**
- [ ] SMTP-Host/Port/User/Passwort/TLS/From/To werden aus Konfiguration genutzt.
- [ ] Erfolgs- und Fehlerfall werden eindeutig signalisiert.
- [ ] Fehlerfälle führen nicht zu stillen Erfolgen.
- [ ] Unit-Tests decken Versand-Erfolg und typische SMTP-Fehler ab.

**Betroffene Dateien / Module / Pfade**
- `movacar_alert/mailer.py`
- `tests/test_mailer_smtp.py`

**Abhängigkeiten**
- T-SETUP-01

**Ausführung**
- **Parallelisierbar** zu T-MAIL-01

**Referenzen**
- Plan: Abschnitt 3 (`mailer`), 5.1, 8.1, 8.3, 10 (SMTP-Open-Item)
- Spec: Abschnitt 2, 7

---

## T-LOG-01 — JSON-Logging-Kontrakt implementieren

**Beschreibung**  
Implementiere strukturiertes JSON-Logging mit Pflichtfeldern und den im Plan genannten Schlüssel-Events.

**Acceptance Criteria**
- [ ] Logevents enthalten `timestamp`, `level`, `event`, `cycle_id`, `message`.
- [ ] Levels `INFO`, `WARN`, `ERROR` sind konsistent nutzbar.
- [ ] Relevante Events sind abdeckbar (Zyklusstart/-ende, API, Delta-Zahlen, Mail, DB-Operationen).
- [ ] Standardausgabe ist stdout; optionales Datei-Logging via Config ist anschließbar.
- [ ] Tests prüfen Event-Feldstruktur und Event-Typ-Konsistenz.

**Betroffene Dateien / Module / Pfade**
- `movacar_alert/logging_utils.py` (oder integriertes Logging-Modul)
- `tests/test_logging_contract.py`

**Abhängigkeiten**
- T-SETUP-01

**Ausführung**
- **Parallelisierbar** zu API/DB/Mail-Tasks

**Referenzen**
- Plan: Abschnitt 8.2, 8.3
- Spec: Abschnitt 8 (Stabilitätsziel)

---

## T-LOOP-01 — Haupt-Loop-Orchestrierung implementieren

**Beschreibung**  
Implementiere den vollständigen Polling-Zyklus mit Modulverkettung, Entscheidungslogik, Persistenzregel und Sleep-Steuerung.

**Acceptance Criteria**
- [ ] Zyklusreihenfolge entspricht dem Plan (Fetch -> Parse -> Highlight -> State -> Delta -> Mail/No-Mail -> DB-Write/Cleanup -> Sleep).
- [ ] Wenn keine neuen Angebote: kein Mailversand, nur Cleanup entfernter IDs.
- [ ] Wenn neue Angebote: Mailversand vor DB-Insert neuer IDs.
- [ ] Bei SMTP-Fehler werden neue IDs nicht persistiert.
- [ ] API-/Parsing-Fehler beenden den Prozess nicht; nächster Zyklus läuft regulär.
- [ ] Tests decken den No-New- und New-Branch sowie SMTP-Fehlerpfad ab.

**Betroffene Dateien / Module / Pfade**
- `movacar_alert/loop.py`
- `movacar_alert/main.py`
- `tests/test_loop_orchestration.py`

**Abhängigkeiten**
- T-DB-02
- T-API-01
- T-PARSE-01
- T-DOMAIN-02
- T-MAIL-01
- T-MAIL-02
- T-LOG-01

**Ausführung**
- **Sequenziell** nach den Kernmodulen

**Referenzen**
- Plan: Abschnitt 3 (`loop`), 6, 8.1
- Spec: Abschnitt 5, 7, 8

---

## T-FLOW-01 — End-to-End-Ablaufkonsistenz absichern

**Beschreibung**  
Implementiere Integrationsszenarien, die den gesamten spezifizierten Ablauf und die zentralen Garantien Ende-zu-Ende absichern.

**Acceptance Criteria**
- [ ] Integrationsfall: neues Angebot triggert genau einen Mailversand und persistiert danach in DB.
- [ ] Integrationsfall: bereits bekanntes Angebot triggert keine „neu“-Mail.
- [ ] Integrationsfall: entfernte Angebote werden aus DB bereinigt.
- [ ] Integrationsfall: SMTP-Fehler verhindert Persistenz neuer IDs.
- [ ] Tests verwenden `tests/example_response.json` als Basisfixture (ggf. mit gezielten Variationen).

**Betroffene Dateien / Module / Pfade**
- `tests/test_end_to_end_flow.py`
- `tests/example_response.json` (nur als Fixture/Read-only)

**Abhängigkeiten**
- T-LOOP-01

**Ausführung**
- **Sequenziell** als Abschluss-Task

**Referenzen**
- Plan: Abschnitt 6, 8.1
- Spec: Abschnitt 4, 5, 7, 8

---

## Open Items (aus Plan übernommen, vor/bei Implementierung zu klären)

1. SMTP-Transportparameter (STARTTLS/SSL, Port-Standard).
2. Genaue HTML-Detailstruktur und Markierungsstil für Highlight.
3. Konkrete Timeout-/Retry-/Backoff-Werte.
4. Zeitzonenpolitik für Datumsvergleich (`UTC` vs lokale Zeit).
5. Verhalten bei kritischen DB-Fehlern (Fail-fast vs kontrolliertes Weiterlaufen).

Diese Punkte sind bewusst als Klärbedarf markiert und nicht implizit entschieden.
