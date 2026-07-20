# Tasks v3.0: Zusätzlicher Anbieter (Imoova) und anbieterspezifischer Versand

## 1. Status und Grundlagen

**Status:** Abgeleitet und zur Umsetzung bereit
**Datum:** 2026-07-20
**SDD-Phase:** TASK
**Primäre Quelle:** `SDD/plan_v3.0.md`
**Validierungsquelle:** `SDD/spec_v3.0.md`

Diese Task-Spezifikation zerlegt den freigegebenen Plan in kleine,
programmierbare und testbare Einheiten. Sie führt keine zusätzlichen Features
ein. Alle Aufgaben bauen auf den verbindlichen Entscheidungen aus Abschnitt 2
von `plan_v3.0.md` auf. Der technische Fix des bestehenden Movacar-Link-Fehlers
ist wie in Plan Abschnitt 2/11.3/12 festgelegt **nicht** Teil dieser Liste; der
Nutzer behebt ihn separat außerhalb dieses Umsetzungszyklus.

## 2. Kurzfassung des Plans

Das Zielsystem erweitert die bestehende, reise-basierte Anwendung um einen
zweiten, unabhängigen Angebots-Anbieter (Imoova) neben Movacar. Jede Reise
erhält eine explizite Anbieterzuordnung (`movacar`, `imoova` oder `both`). Für
jede Reise wird pro zugeordnetem Anbieter eine eigene, fehlerisolierte Abfrage
durchgeführt; Sofortbenachrichtigungen und geplante Übersichten werden je
Anbieter in getrennten E-Mails versendet. Die Zuordnung einer Reise zu einer
Imoova-Area erfolgt über einen Punkt-in-Polygon-Test der Reisekoordinaten
gegen in `config/imoova_areas.json` hinterlegte Area-Polygone.

## 3. Workstreams

| ID | Workstream | Ziel |
|---|---|---|
| WS1 | Domäne und Persistenz | Anbieterbezogene Zustände, Schema und sichere Migrationen bereitstellen. |
| WS2 | Areal-Zuordnung | Polygon-basierte Areal-Konfiguration, Resolver und OSM-Erzeugungsskript bereitstellen. |
| WS3 | Imoova-API-Integration | Antwortformat verifizieren, Client und Parser für Imoova bereitstellen. |
| WS4 | Anbieterbezogene Persistenz und Synchronisierung | Verfügbarkeitsabgleich und Synchronisierung strikt je Anbieter isolieren. |
| WS5 | Benachrichtigungen je Anbieter | Mailansicht, Sofort- und Übersichtsversand sowie Templates anbieterbezogen umsetzen. |
| WS6 | Orchestrierung, Konfiguration, CLI | Polling-Loop, Settings und Verwaltungs-CLI um den Anbieter erweitern. |
| WS7 | Qualität und Betrieb | Bestehende und neue Tests, E2E-Abdeckung und Dokumentation vervollständigen. |

## 4. Geklärte Planannahmen

| Thema | Verbindliche Klarstellung | Betroffene Tasks |
|---|---|---|
| Punkt-in-Polygon-Implementierung | `shapely` wird als neue Dependency in `requirements.txt` aufgenommen und für den Polygon-Test verwendet (keine eigene Ray-Casting-Implementierung). | T05, T22 |
| Imoova-API-Verifikation | Eine eigene, vorgezogene Aufgabe (T07) verifiziert Endpunkt, Query-Parameter und Antwortformat per echtem Testaufruf und blockiert den Parser (T09); dieser wird erst nach Abschluss von T07 final spezifiziert. | T07, T09 |
| OSM-Areal-Skript | Das Skript nutzt direkte HTTP-Anfragen an die Overpass API zur Grenzabfrage; keine zusätzliche Python-GIS-Bibliothek (z. B. kein `osmnx`). | T06 |

## 5. Task-Liste

### Aufwand- und Relevanzkategorien

| Kategorie | Einordnung |
|---|---|
| Luna | Niedriger bis überschaubarer Aufwand oder klar abgegrenzter Systembeitrag. |
| Terra | Mittlerer Aufwand und relevante, aber isoliert umsetzbare Systemfunktion. |
| Sol | Außergewöhnlich hoher Aufwand und zugleich zentral für den vollständigen Zielablauf. |

### T01 - Provider- und TripProviderSelection-Domänenmodell definieren

**Workstream:** WS1
**Kategorie:** Luna
**Beschreibung:** Ein `Provider`-Enum (`movacar`, `imoova`) für die tatsächliche
Angebotsquelle sowie ein `TripProviderSelection`-Enum (`movacar`, `imoova`,
`both`) für die Anbieterzuordnung einer Reise definieren, inklusive einer
Auflösungsmethode von `TripProviderSelection` in ein oder zwei `Provider`-Werte.
`Trip` erhält ein verpflichtendes Feld `provider` mit Default `movacar`;
`Offer` erhält ein verpflichtendes Feld `provider`.

**Acceptance Criteria:**

- `Provider` kennt ausschließlich `movacar` und `imoova`.
- `TripProviderSelection` kennt `movacar`, `imoova` und `both` und lässt sich eindeutig in ein oder zwei `Provider`-Werte auflösen.
- Bestehende und neu angelegte Reisen ohne explizite Angabe erhalten `provider = movacar`.
- `Offer` besitzt ein verpflichtendes `provider`-Feld ohne Default.

**Betroffene Dateien/Pfade:** `src/models/trip.py`, `src/models/offer.py`, `tests/test_models_offer.py`, neue Domänentests unter `tests/`
**Abhängigkeiten:** Keine
**Ausführung:** Parallelisierbar

### T02 - Schema-Migration auf Version 5 (anbieterbezogene Spalten)

**Workstream:** WS1
**Kategorie:** Terra
**Beschreibung:** Eine additive, transaktionale und idempotente Migration auf
`SCHEMA_VERSION = 5` bereitstellen, die `offers.provider`, `trips.provider` und
`trip_overview_slots.provider` ergänzt (jeweils `NOT NULL DEFAULT 'movacar'`),
sowie einen neuen eindeutigen Index für `trip_overview_slots` auf
`(trip_id, local_date, slot_hour, provider)`.

**Acceptance Criteria:**

- Bestehende Zeilen aller drei Tabellen werden automatisch auf `provider = 'movacar'` befüllt.
- Eine bereits migrierte Datenbank bleibt bei erneutem Lauf unverändert.
- Eine fehlgeschlagene Migration hinterlässt kein teilweise aktiviertes Schema.
- Der Dienst startet das Polling erst nach erfolgreicher Migration.

**Betroffene Dateien/Pfade:** `src/storage/sqlite_store.py`, `tests/test_sqlite_schema.py`
**Abhängigkeiten:** T01
**Ausführung:** Sequentiell

### T03 - Angebots-ID-Namensraum für Imoova sicherstellen

**Workstream:** WS1
**Kategorie:** Luna
**Beschreibung:** Sicherstellen, dass Angebote mit `provider = imoova`
verpflichtend eine mit `imoova:` präfixierte ID besitzen, während bestehende
Movacar-IDs unverändert und unpräfixiert bleiben (kein Rename, keine
Datenmigration bestehender Zeilen).

**Acceptance Criteria:**

- Eine Validierung weist ein `Offer` mit `provider = imoova` und einer ID ohne `imoova:`-Präfix zurück.
- Bestehende Movacar-IDs werden durch diese Aufgabe nicht verändert.
- `offers.id` bleibt nach Einführung von Imoova global eindeutig.

**Betroffene Dateien/Pfade:** `src/models/offer.py`, `tests/test_models_offer.py`
**Abhängigkeiten:** T01
**Ausführung:** Parallelisierbar

### T04 - Areal-Konfigurationsformat und Resolver-Schnittstelle definieren

**Workstream:** WS2
**Kategorie:** Luna
**Beschreibung:** Das JSON-Format von `config/imoova_areas.json` (Liste von
Areas mit Name und geografischem Polygon als Lat/Long-Koordinatenliste) sowie
die Domänenschnittstelle `resolve_area(latitude, longitude) -> str | None`
festlegen.

**Acceptance Criteria:**

- Das Dateiformat erlaubt beliebig viele Areas mit je einem Namen und einem Polygon.
- Die Schnittstelle nimmt Lat/Long entgegen und liefert einen Area-Namen oder `None`.
- Eine Beispieldatei mit mindestens einer Area liegt im Repository vor.

**Betroffene Dateien/Pfade:** `config/imoova_areas.json` (Beispiel/Schema), neues Modulverzeichnis `src/areas/`
**Abhängigkeiten:** Keine
**Ausführung:** Parallelisierbar

### T05 - Punkt-in-Polygon-Resolver mit shapely implementieren

**Workstream:** WS2
**Kategorie:** Terra
**Beschreibung:** `resolve_area` unter Verwendung von `shapely` implementieren:
`config/imoova_areas.json` wird beim Programmstart einmalig geladen, die
übergebenen Reisekoordinaten werden per `shapely.geometry.Point`/`Polygon`
gegen alle hinterlegten Area-Polygone getestet.

**Acceptance Criteria:**

- `shapely` ist als neue Dependency in `requirements.txt` eingetragen.
- Liegt ein Koordinatenpaar in genau einem Polygon, wird dessen Area-Name geliefert.
- Liegt ein Koordinatenpaar in keinem Polygon, wird `None` geliefert.
- Eine fehlende oder fehlerhafte Konfigurationsdatei führt zu einem klar unterscheidbaren, protokollierten Zustand statt eines unkontrollierten Absturzes.

**Betroffene Dateien/Pfade:** `src/areas/imoova_area_resolver.py`, `requirements.txt`, `tests/test_imoova_area_resolver.py`
**Abhängigkeiten:** T04
**Ausführung:** Sequentiell

### T06 - OSM-basiertes Areal-Polygon-Skript mit Overpass API erstellen

**Workstream:** WS2
**Kategorie:** Terra
**Beschreibung:** Ein eigenständiges, wiederholbar ausführbares Skript
bereitstellen, das für jede Imoova-Area per direkter HTTP-Anfrage an die
Overpass API die geografische Grenze abfragt und `config/imoova_areas.json`
erzeugt beziehungsweise aktualisiert. Läuft nicht im Polling-Pfad.

**Acceptance Criteria:**

- Das Skript ist ohne zusätzliche Python-GIS-Bibliothek (kein `osmnx`) lauffähig.
- Ein erneuter Lauf mit unveränderten Areas erzeugt eine inhaltlich stabile Datei.
- Netzwerk- oder Antwortfehler der Overpass API werden sichtbar gemeldet, ohne eine bereits bestehende, gültige Konfigurationsdatei zu beschädigen.

**Betroffene Dateien/Pfade:** `scripts/build_imoova_area_mapping.py`, `README.md`
**Abhängigkeiten:** T04
**Ausführung:** Parallelisierbar

### T07 - Imoova-API-Antwortformat live verifizieren (Blocker für T09)

**Workstream:** WS3
**Kategorie:** Terra
**Beschreibung:** Einen echten Testaufruf gegen die reale Imoova-API
durchführen (Endpunkt `relocations/{area}`, Parameter `earliest_departure`)
und das vollständige Antwortformat für Route, Zeitraum, Preis, Verfügbarkeit
und Koordinaten dokumentieren. Diese Aufgabe erzeugt keinen Produktionscode,
sondern die verbindliche Grundlage für T09.

**Acceptance Criteria:**

- Mindestens ein realer, erfolgreicher Testaufruf mit gültiger Area und Datum ist durchgeführt und dokumentiert.
- Die Dokumentation deckt Feldnamen, Verschachtelung, Einheiten und Koordinatengenauigkeit für alle in Abschnitt 7.2 von `plan_v3.0.md` genannten Zielfelder ab.
- Abweichungen von der bisherigen Annahme (`plan_v3.0.md` §7.1) sind explizit benannt.
- Das Ergebnis ist für T09 ohne Rückfragen direkt verwendbar.

**Betroffene Dateien/Pfade:** neue Verifikationsnotiz (z. B. `docs/imoova_api_notes.md`), keine Änderung an Produktionscode
**Abhängigkeiten:** Keine
**Ausführung:** Sequentiell

### T08 - Imoova-Client (Request-Bildung, Retry, Fehlerbehandlung) implementieren

**Workstream:** WS3
**Kategorie:** Terra
**Beschreibung:** `build_imoova_trip_url(imoova_api_url, area, trip)` und
`fetch_imoova_offers(settings, trip, area)` strukturell analog zum
Movacar-Client bereitstellen: URL-Muster
`{imoova_api_url}/relocations/{area}?earliest_departure={date}` mit
`date = trip.pickup_start` in identischer Syntax wie bei Movacar, keine
Authentifizierung, gleiche Retry-Delays `(1, 2, 4)` Sekunden wie Movacar,
eigene `ImoovaApiError`-Fehlerklassen-Hierarchie.

**Acceptance Criteria:**

- Die erzeugte URL folgt exakt dem bestätigten Muster ohne zusätzliche Header oder Tokens.
- `earliest_departure` verwendet denselben Datumswert und dieselbe Syntax wie `trip.pickup_start`.
- Transport- und Antwortfehler sind über spezifische `ImoovaApiError`-Subklassen unterscheidbar.
- Retry-Verhalten wird pro Reise-Request ausgeführt und entspricht dem Movacar-Client.

**Betroffene Dateien/Pfade:** `src/api/imoova_client.py`, `tests/test_imoova_client.py`
**Abhängigkeiten:** T01
**Ausführung:** Parallelisierbar

### T09 - Imoova-Antwort-Parser gemäß verifiziertem Format implementieren

**Workstream:** WS3
**Kategorie:** Terra
**Beschreibung:** `parse_imoova_offers(response)` gemäß dem in T07
dokumentierten, verifizierten Antwortformat implementieren: All-or-nothing-
Validierung wie beim Movacar-Parser, jedes erzeugte `Offer` erhält
`provider = imoova` und eine mit `imoova:` präfixierte ID.

**Acceptance Criteria:**

- Eine vollständige, valide Antwort erzeugt für jedes Angebot ein korrektes `Offer` mit `provider = imoova` und präfixierter ID.
- Ein unvollständig auflösbares Angebot invalidiert die gesamte Antwort (All-or-nothing).
- Die Feldzuordnung entspricht exakt dem in T07 dokumentierten Format, nicht der ursprünglichen Annahme aus der Planphase.

**Betroffene Dateien/Pfade:** `src/parser/imoova_offer_parser.py`, `tests/test_imoova_offer_parser.py`
**Abhängigkeiten:** T01, T03, T07
**Ausführung:** Sequentiell

### T10 - Anbieterbezogene Synchronisierungs- und Verfügbarkeits-Methoden im Repository

**Workstream:** WS4
**Kategorie:** Sol
**Beschreibung:** `synchronize_trip_offers`, `reconcile_trip_offer_availability`,
`list_new_unsent_available_trip_offers` und `list_available_trip_offers` in
`sqlite_store.py` um einen verpflichtenden `provider`-Parameter erweitern und
so umbauen, dass Lesen, Schreiben und Verfügbarkeitsabgleich ausschließlich
innerhalb dieses Anbieters für die jeweilige Reise erfolgen.

**Acceptance Criteria:**

- Eine vollständige Antwort eines Anbieters markiert ausschließlich Zuordnungen desselben Anbieters derselben Reise als nicht verfügbar.
- Zuordnungen des jeweils anderen Anbieters derselben Reise bleiben in jedem Fall unverändert.
- Alle vier genannten Methoden verweigern den Aufruf ohne `provider`-Parameter.
- Bestehende Movacar-Zuordnungen und deren Verfügbarkeits-/Versandzustand bleiben nach Einführung des Parameters unverändert.

**Betroffene Dateien/Pfade:** `src/storage/sqlite_store.py`, `tests/test_sqlite_store_ops.py`
**Abhängigkeiten:** T02
**Ausführung:** Sequentiell

### T11 - Reise-Synchronisierer um Provider-Parameter erweitern

**Workstream:** WS4
**Kategorie:** Terra
**Beschreibung:** `synchronize_trip_offers(store, trip, offers)` in
`trip_offer_synchronizer.py` um einen `provider`-Parameter erweitern und an die
in T10 angepassten Repository-Methoden durchreichen. Wird pro Anbieter einer
Reise separat aufgerufen.

**Acceptance Criteria:**

- Der Aufruf ohne `provider`-Parameter ist nicht mehr möglich.
- Distanzberechnung bleibt unverändert anbieterunabhängig (Haversine).
- Ein Aufruf für Anbieter A verändert nachweislich keine Zuordnungen von Anbieter B derselben Reise.

**Betroffene Dateien/Pfade:** `src/synchronization/trip_offer_synchronizer.py`, `tests/test_trip_offer_synchronizer.py`
**Abhängigkeiten:** T10
**Ausführung:** Sequentiell

### T12 - Übersichtsslot-Persistenz um Provider erweitern

**Workstream:** WS4
**Kategorie:** Luna
**Beschreibung:** Die Store-Methoden für Übersichtsslots (`has_trip_overview_slot`,
`mark_trip_overview_slot_sent` oder äquivalent) um einen `provider`-Parameter
erweitern, sodass für dieselbe Reise beide Anbieter unabhängig ihren
09:00/21:00-Slot verwalten. Die Zeitplanlogik (`latest_due_summary_slot`)
bleibt unverändert.

**Acceptance Criteria:**

- Ein bereits gesendeter Slot für Anbieter A blockiert nicht den identischen Slot für Anbieter B derselben Reise.
- Der neue eindeutige Index aus T02 wird korrekt genutzt.
- Bestehendes Movacar-Slot-Verhalten bleibt nach der Erweiterung unverändert.

**Betroffene Dateien/Pfade:** `src/storage/sqlite_store.py`, `src/loop/summary_schedule.py`, `tests/test_sqlite_store_ops.py`
**Abhängigkeiten:** T02
**Ausführung:** Parallelisierbar

### T13 - TripMailView und prepare_trip_mail_view um Provider erweitern

**Workstream:** WS5
**Kategorie:** Terra
**Beschreibung:** `TripMailView` erhält ein zusätzliches Feld `provider`;
`prepare_trip_mail_view` erhält einen verpflichtenden `provider`-Parameter und
liest ausschließlich Angebote dieses Anbieters für die betreffende Reise.

**Acceptance Criteria:**

- `TripMailView` validiert, dass alle enthaltenen `TripOfferView`-Einträge zum angegebenen `provider` gehören.
- `prepare_trip_mail_view` liefert für Anbieter A niemals Angebote von Anbieter B derselben Reise.
- Bestehende Feldstruktur (Empfänger, neue/verfügbare Angebote, `offers_url`) bleibt inhaltlich erhalten.

**Betroffene Dateien/Pfade:** `src/notifications/trip_mail_view.py`, `tests/test_trip_mail_view.py`
**Abhängigkeiten:** T10
**Ausführung:** Sequentiell

### T14 - Sofortbenachrichtigung und Übersicht anbieterbezogen versenden

**Workstream:** WS5
**Kategorie:** Terra
**Beschreibung:** `send_instant_trip_notification` und `send_due_trip_summary`
um einen verpflichtenden `provider`-Parameter erweitern, an
`prepare_trip_mail_view` durchreichen und den E-Mail-Betreff um die
Anbieterbezeichnung ergänzen.

**Acceptance Criteria:**

- Eine Reise mit `both` kann pro Zyklus bis zu zwei unabhängige Sofortmails und zu zwei unabhängige Übersichtsmails erzeugen.
- Versandstatus wird ausschließlich für den aufgerufenen Anbieter aktualisiert.
- Der Betreff zeigt sichtbar den erzeugenden Anbieter.
- Ein SMTP-Fehler für einen Anbieter lässt einen erneuten Zustellversuch im nächsten Durchlauf zu, ohne den anderen Anbieter zu beeinflussen.

**Betroffene Dateien/Pfade:** `src/notifications/instant_notification.py`, `src/notifications/trip_summary.py`, `tests/test_instant_notification.py`, `tests/test_trip_summary.py`
**Abhängigkeiten:** T12, T13
**Ausführung:** Sequentiell

### T15 - Templates auf dynamische Anbieterbezeichnung umstellen

**Workstream:** WS5
**Kategorie:** Luna
**Beschreibung:** `templates.py` so anpassen, dass Titel und Kopfbereich die
Anbieterbezeichnung dynamisch aus `view.provider` rendern, statt fest auf
„Movacar“ verdrahtet zu sein.

**Acceptance Criteria:**

- Für `provider = movacar` bleibt die bisherige Darstellung unverändert.
- Für `provider = imoova` erscheint „Imoova“ sichtbar in Titel und Kopfbereich.
- HTML-Struktur und Distanzstufen-Darstellung bleiben unverändert.

**Betroffene Dateien/Pfade:** `src/mailer/templates.py`, `tests/test_mail_templates.py`
**Abhängigkeiten:** T13
**Ausführung:** Parallelisierbar

### T16 - Settings um Imoova-Konfiguration erweitern

**Workstream:** WS6
**Kategorie:** Luna
**Beschreibung:** `Settings` um `imoova_api_url: str | None` und
`imoova_areas_path: Path` (Default `config/imoova_areas.json`) erweitern. Ist
`imoova_api_url` nicht gesetzt, wird Imoova für alle Reisen deaktiviert und
dies sichtbar protokolliert.

**Acceptance Criteria:**

- Ein Dienststart ohne `IMOOVA_API_URL` bleibt möglich; Imoova ist dann inaktiv, unabhängig von `trip.provider`.
- Ein gesetzter Wert wird korrekt geladen und an den Imoova-Client durchgereicht.
- `imoova_areas_path` verwendet den dokumentierten Default, ist aber überschreibbar.

**Betroffene Dateien/Pfade:** `src/config/settings.py`, `tests/test_settings.py`
**Abhängigkeiten:** Keine
**Ausführung:** Parallelisierbar

### T17 - Polling-Loop zu anbieterbezogener Schleife pro Reise umbauen

**Workstream:** WS6
**Kategorie:** Sol
**Beschreibung:** `_process_one_trip` in `poll_loop.py` von einem einzelnen
Verarbeitungspfad zu einer inneren Schleife über die aus `trip.provider`
aufgelösten `Provider`-Werte umbauen. Jede Iteration (Movacar/Imoova) ist
vollständig fehlerisoliert; fehlt für Imoova eine Areal-Zuordnung, wird dieser
Anbieter für die Reise übersprungen und protokolliert.

**Acceptance Criteria:**

- Eine Reise mit `both` durchläuft pro Zyklus zwei vollständig unabhängige Unterabläufe.
- Ein Fehler im Imoova-Unterablauf einer Reise verhindert nicht die erfolgreiche Verarbeitung des Movacar-Unterablaufs derselben Reise und umgekehrt.
- Fehlende Areal-Zuordnung führt zu einem protokollierten, übersprungenen Imoova-Unterablauf ohne Fehlerstatus.
- Bestehendes Movacar-only-Verhalten (Reisen ohne explizite Angabe) bleibt beobachtbar unverändert.

**Betroffene Dateien/Pfade:** `src/loop/poll_loop.py`, `tests/test_poll_loop.py`
**Abhängigkeiten:** T05, T08, T09, T11, T14, T16
**Ausführung:** Sequentiell

### T18 - Verwaltungs-CLI um Provider-Optionen erweitern

**Workstream:** WS6
**Kategorie:** Terra
**Beschreibung:** `trip create` um eine optionale `--provider`-Option (Default
`movacar`) ergänzen und einen neuen Unterbefehl `trip provider set --trip-id
--provider` einführen, der die Anbieterzuordnung einer bestehenden Reise
ändert. `trip list` gibt den Anbieter mit aus.

**Acceptance Criteria:**

- `trip create` ohne `--provider` erzeugt weiterhin eine reine Movacar-Reise.
- Ungültige Anbieterwerte enden mit nachvollziehbarer Meldung und nicht-null Exit-Code.
- `trip provider set` aktualisiert `trips.provider` transaktional und weist unbekannte Reisen mit nicht-null Exit-Code zurück.
- `trip list` zeigt den Anbieter je Reise in Text- und JSON-Ausgabe.

**Betroffene Dateien/Pfade:** `src/admin_cli.py`, `src/storage/sqlite_store.py`, `tests/test_admin_cli.py`, `README.md`
**Abhängigkeiten:** T01, T10
**Ausführung:** Sequentiell

### T19 - Bestehende Tests auf Provider-Parameter umstellen

**Workstream:** WS7
**Kategorie:** Terra
**Beschreibung:** Bestehende Tests für `sqlite_store.py`, `poll_loop.py`,
`trip_mail_view.py`, `instant_notification.py`, `trip_summary.py` und
`templates.py` um den `provider`-Parameter beziehungsweise die
anbieterabhängige Erwartung ergänzen, inklusive expliziter Prüfung, dass ein
Movacar-Vorgang niemals Imoova-Zustand verändert und umgekehrt.

**Acceptance Criteria:**

- Alle betroffenen Bestandstests laufen mit dem neuen `provider`-Parameter grün.
- Mindestens ein Test je betroffener Komponente prüft die Anbieterisolation explizit.
- Kein Bestandstest für reines Movacar-Verhalten wird ohne Ersatz entfernt.

**Betroffene Dateien/Pfade:** `tests/test_sqlite_store_ops.py`, `tests/test_poll_loop.py`, `tests/test_trip_mail_view.py`, `tests/test_instant_notification.py`, `tests/test_trip_summary.py`, `tests/test_mail_templates.py`
**Abhängigkeiten:** T10, T13, T14, T15, T17
**Ausführung:** Sequentiell

### T20 - Neue Unit-Tests gemäß Plan-Teststrategie ergänzen

**Workstream:** WS7
**Kategorie:** Terra
**Beschreibung:** Die in Abschnitt 10.2 von `plan_v3.0.md` aufgezählten neuen
Testfälle ergänzen: Migration auf Version 5, `TripProviderSelection`-
Auflösung, Imoova-Client, Imoova-Parser, Areal-Resolver, anbieterbezogene
Synchronisierung/Reconciliation, getrennte Mails je Anbieter, CLI-Erweiterungen.

**Acceptance Criteria:**

- Jeder in `plan_v3.0.md` §10.2 aufgezählte Mindestfall ist automatisiert abgedeckt.
- Kein Test kontaktiert echte externe Dienste (Imoova, Movacar, Overpass).
- Jeder neue oder geänderte Fachvertrag aus WS1–WS6 besitzt mindestens einen passenden Unit-Test.

**Betroffene Dateien/Pfade:** `tests/test_sqlite_schema.py`, `tests/test_imoova_area_resolver.py`, `tests/test_imoova_client.py`, `tests/test_imoova_offer_parser.py`, `tests/test_admin_cli.py`, neue Tests unter `tests/`
**Abhängigkeiten:** T02, T03, T05, T08, T09, T18
**Ausführung:** Sequentiell

### T21 - Erweiterten hermetischen E2E-Test mit Movacar- und Imoova-Doubles erstellen

**Workstream:** WS7
**Kategorie:** Sol
**Beschreibung:** Den bestehenden E2E-Test um mindestens die in
`plan_v3.0.md` §10.3 genannten Szenarien erweitern: eine Reise mit `both` und
unterschiedlichen Test-Doubles, ein isolierter Fehler in einem
Anbieter-Unterablauf, eine Reise ohne Areal-Zuordnung, unabhängige
09:00/21:00-Slots je Anbieter.

**Acceptance Criteria:**

- Eine Reise mit `provider = both` erzeugt im Test zwei unabhängige, korrekt zugeordnete Erstbenachrichtigungen.
- Ein simulierter Fehler im Imoova-Unterablauf verhindert im Test nicht den erfolgreichen Movacar-Versand derselben Reise, und umgekehrt.
- Eine Reise mit `provider = imoova` ohne passendes Area-Polygon erzeugt im Test keinen Imoova-Request und keine Imoova-Mail.
- Der Test kontaktiert weder Gmail, Movacar, Imoova, Overpass/OpenStreetMap noch einen anderen externen Dienst.

**Betroffene Dateien/Pfade:** `tests/test_end_to_end_flow.py`, Test-Doubles/Fixtures unter `tests/`, `src/main.py`, `src/loop/poll_loop.py`
**Abhängigkeiten:** T17, T19, T20
**Ausführung:** Sequentiell

### T22 - Dokumentation aktualisieren

**Workstream:** WS7
**Kategorie:** Luna
**Beschreibung:** `README.md` um das Anbieterkonzept, die Imoova-Konfiguration
(`IMOOVA_API_URL`, `IMOOVA_AREAS_PATH`), das Polygon-Format von
`config/imoova_areas.json`, die neue `shapely`-Dependency, die Nutzung des
OSM-Areal-Skripts (Overpass API) sowie die neuen CLI-Optionen ergänzen.

**Acceptance Criteria:**

- Einrichtung und Betrieb mit und ohne konfiguriertes Imoova sind beschrieben.
- Das Polygon-Format der Areal-Konfigurationsdatei ist mit Beispiel dokumentiert.
- Die neuen CLI-Befehle (`trip create --provider`, `trip provider set`) sind mit Beispielaufrufen dokumentiert.
- Die Ausführung des OSM-Areal-Skripts ist beschrieben, inklusive Hinweis, dass es nicht im Polling-Pfad läuft.

**Betroffene Dateien/Pfade:** `README.md`, `.env.example` falls vorhanden, `requirements.txt`
**Abhängigkeiten:** T05, T06, T16, T18
**Ausführung:** Parallelisierbar

## 6. Abhängigkeits- und Ausführungsregel

„Parallelisierbar“ bedeutet, dass die Aufgabe nach Erfüllung ihrer angegebenen
Abhängigkeiten unabhängig von anderen parallelisierbaren Aufgaben umgesetzt
werden kann. „Sequentiell“ kennzeichnet Aufgaben, deren Änderungsscope oder
fachlicher Zustand eine geordnete Umsetzung erfordert. T07 blockiert T09
unabhängig von dieser allgemeinen Regel explizit, da der Parser ohne
verifiziertes Antwortformat nicht sinnvoll final spezifiziert werden kann.
