# Tasks v2.1: Reise-basierte Zielarchitektur und Systemintegration

## 1. Status und Grundlagen

**Status:** Abgeleitet und zur Umsetzung bereit  
**Datum:** 2026-07-15  
**SDD-Phase:** TASK  
**Primäre Quelle:** `SDD/plan_v2.1.md`  
**Validierungsquelle:** `SDD/spec_v2.0.md`

Diese Task-Spezifikation zerlegt den freigegebenen Plan in kleine,
programmierbare und testbare Einheiten. Sie führt keine zusätzlichen Features
ein. Alle Aufgaben bauen auf den verbindlichen Entscheidungen aus Abschnitt 2
von `plan_v2.1.md` auf.

## 2. Kurzfassung des Plans

Das Zielsystem verwaltet mehrere persistierte Reisen mit jeweils eigenen
Zeiträumen, Startkoordinaten und Empfängern. Der Dienst pollt die
Movacar-kompatible API pro Reise, verwaltet Angebote global und deren Zustand
pro Reise, bewertet Entfernungen und versendet reisespezifische
Sofortbenachrichtigungen sowie Übersichten. Die bisherige globale
Matching-, Empfänger- und Highlighting-Logik wird abgelöst.

## 3. Workstreams

| ID | Workstream | Ziel |
|---|---|---|
| WS1 | Domäne und Persistenz | Reisebezogene Zustände, Schema und sichere Migrationen bereitstellen. |
| WS2 | Reiseverwaltung | Validierte Reise- und Empfängeroperationen über eine CLI ermöglichen. |
| WS3 | Angebotsverarbeitung | Reisezeiträume abfragen, Angebote zuordnen und deren Verfügbarkeit verwalten. |
| WS4 | Benachrichtigungen | Reise-Mailansichten, SMTP-Versand und Übersichtsslots bereitstellen. |
| WS5 | Laufzeit und Konfiguration | Den Dienst zum fehlerisolierten Reise-Orchestrator umstellen. |
| WS6 | Qualität und Betrieb | Veraltete Verträge ablösen, Tests und Dokumentation vollständig aktualisieren. |

## 4. Geklärte Planannahmen

| Thema | Verbindliche Klarstellung | Betroffene Tasks |
|---|---|---|
| Movacar-Zeitraumvertrag | Der Request verwendet `locale=en`, `pickupDateFrom=YYYY-MM-DD` und `pickupDateTo=YYYY-MM-DD`. | T09, T23 |
| Migrationsanschluss | `SQLiteStore.initialize_schema` wird bereits vor dem Polling aufgerufen, enthält aber noch keine Versionsmetadaten oder Migrationen. Die versionierte Migration wird dort eingeführt. | T02, T03, T04 |
| Gmail-Konfiguration | Das App-Passwort wird manuell und ausschließlich als `SMTP_PASSWORD` in der lokalen, nicht versionierten `.env` hinterlegt. | T18, T24 |

## 5. Task-Liste

### Aufwand- und Relevanzkategorien

| Kategorie | Einordnung |
|---|---|
| Luna | Niedriger bis überschaubarer Aufwand oder klar abgegrenzter Systembeitrag. |
| Terra | Mittlerer Aufwand und relevante, aber isoliert umsetzbare Systemfunktion. |
| Sol | Außergewöhnlich hoher Aufwand und zugleich zentral für den vollständigen Zielablauf. |

### T01 - Reise- und Zuordnungsdomänenmodell definieren

**Workstream:** WS1  
**Kategorie:** Luna  
**Beschreibung:** Die reinen Domänenobjekte für Reise, Reiseempfänger,
reisebezogene Angebotsansicht und explizite Distanzstufe festlegen. Das globale
`Offer` bleibt eine unveränderliche API-Repräsentation und enthält keine
reise- oder versandspezifischen Attribute.

**Acceptance Criteria:**

- Reise enthält Identität, Name, Pick-up-Beginn/-Ende, Startstadt, Latitude und Longitude.
- Reise-Angebotsansicht enthält Reise- und Angebotsbezug, ungerundete Distanz, Verfügbarkeits- und Versandstatus sowie Distanzstufe.
- Distanzstufen bilden `<100`, `>=100 und <250`, `>=250 und <500` und `>=500` eindeutig ab.
- `ClassifiedOffer` und boolesches Althighlight sind nicht Teil des neuen Fachvertrags.

**Betroffene Dateien/Pfade:** `src/models/offer.py`, `src/models/`, `tests/test_models_offer.py`, neue domänenbezogene Tests unter `tests/`  
**Abhängigkeiten:** Keine  
**Ausführung:** Parallelisierbar

### T02 - Versioniertes SQLite-Migrationsfundament einführen

**Workstream:** WS1  
**Kategorie:** Terra  
**Beschreibung:** Einen additiven, transaktionalen und idempotenten
Migrationsablauf mit Migrationsmetadaten innerhalb der SQLite-Grenze
definieren und bereitstellen.

**Acceptance Criteria:**

- Ausgeführte Schemaversionen werden persistent und eindeutig erfasst.
- Eine bereits migrierte Datenbank bleibt bei erneutem Lauf unverändert.
- Eine fehlgeschlagene Migration hinterlässt kein teilweise aktiviertes Schema.
- Eine bestehende unversionierte Datenbank mit der alten `offers`-Tabelle wird vor weiteren Migrationen sicher auf eine nachvollziehbare Baseline gesetzt.
- Der Aufrufer kann Polling erst nach erfolgreicher Migration starten.

**Betroffene Dateien/Pfade:** `src/storage/sqlite_store.py`, `src/main.py`, `tests/test_sqlite_schema.py`, neue Migrationstests unter `tests/`  
**Abhängigkeiten:** Keine  
**Ausführung:** Sequentiell

### T03 - Reiseschema und referenzielle Integrität migrieren

**Workstream:** WS1  
**Kategorie:** Terra  
**Beschreibung:** Die Tabellen für Reisen, Empfänger, Reise-Angebot-Zuordnungen
und Übersichtsslots samt eindeutigen Schlüsseln und referenzieller Integrität
als versionierte Migration spezifizieren.

**Acceptance Criteria:**

- `trips`, `trip_recipients`, `trip_offers` und ein Übersichtsslot-Zustand besitzen die im Plan festgelegten Identitäten.
- Empfänger sind je Reise über `(trip_id, normalized_email)` eindeutig.
- Zuordnungen sind über `(trip_id, offer_id)` eindeutig.
- Das Löschen einer Reise entfernt Empfänger, Zuordnungen und Slots, nicht aber globale Angebote.

**Betroffene Dateien/Pfade:** `src/storage/sqlite_store.py`, `tests/test_sqlite_schema.py`, `tests/test_sqlite_store_ops.py`  
**Abhängigkeiten:** T01, T02  
**Ausführung:** Sequentiell

### T04 - Bestehende Angebotshistorie migrationssicher übernehmen

**Workstream:** WS1  
**Kategorie:** Terra  
**Beschreibung:** Die vorhandene globale Angebotstabelle in die Zielhistorie
überführen, ohne Bestandsangebote künstlich Reisen zuzuordnen oder rückwirkend
als versandpflichtig zu behandeln.

**Acceptance Criteria:**

- Vorhandene globale Angebote bleiben nach der Migration lesbar und global eindeutig.
- Die Migration erzeugt keine `trip_offers` für Bestandsangebote.
- Ein späteres Auftreten eines Bestandsangebots in einer Reiseantwort erzeugt für diese Reise eine neue Zuordnung.

**Betroffene Dateien/Pfade:** `src/storage/sqlite_store.py`, `tests/test_sqlite_schema.py`, `tests/test_sqlite_store_ops.py`  
**Abhängigkeiten:** T02, T03  
**Ausführung:** Sequentiell

### T05 - Reise- und Empfänger-Repository bereitstellen

**Workstream:** WS2  
**Kategorie:** Terra  
**Beschreibung:** Die transaktionalen Persistenzoperationen zum Anlegen,
Löschen und Auflisten von Reisen sowie zum Hinzufügen, Entfernen und Auflisten
von Reiseempfängern abgrenzen.

**Acceptance Criteria:**

- Reisen und Empfänger können dauerhaft angelegt und aufgelistet werden.
- Das Löschen einer Reise folgt dem in T03 definierten Löschvertrag.
- Doppelte Empfänger und unbekannte Reisen liefern unterscheidbare Fehler.
- Fachlich zusammengehörige Änderungen erfolgen atomar.

**Betroffene Dateien/Pfade:** `src/storage/sqlite_store.py`, neue Repository-Tests unter `tests/`  
**Abhängigkeiten:** T03  
**Ausführung:** Sequentiell

### T06 - Reise- und Empfängervalidierung bereitstellen

**Workstream:** WS2  
**Kategorie:** Luna  
**Beschreibung:** Fachliche Validierung für Namen, Pick-up-Zeiträume,
Startstadt, verpflichtende Koordinaten und normalisierte E-Mail-Adressen
festlegen.

**Acceptance Criteria:**

- Leere oder ungültige Namen, Städte, Zeiträume und Koordinaten werden abgewiesen.
- Der Zeitraum ist nur bei zulässigem Beginn und Ende gültig.
- E-Mail-Adressen werden vor der Eindeutigkeitsprüfung normalisiert und validiert.
- Fehler sind für die CLI verständlich unterscheidbar.

**Betroffene Dateien/Pfade:** neue Verwaltungs- oder Validierungskomponente unter `src/`, neue Validierungstests unter `tests/`  
**Abhängigkeiten:** T01  
**Ausführung:** Parallelisierbar

### T07 - Verwaltungs-CLI für Reisen bereitstellen

**Workstream:** WS2  
**Kategorie:** Terra  
**Beschreibung:** Die CLI-Unterbefehle zum Anlegen, Löschen und Auflisten von
Reisen mit lesbarer und optionaler JSON-Ausgabe umsetzen.

**Acceptance Criteria:**

- Reisen können mit allen verpflichtenden Daten angelegt, gelöscht und aufgelistet werden.
- Die CLI unterstützt lesbare Ausgabe und optional JSON.
- Ungültige Eingaben, unbekannte Reisen und Persistenzfehler enden mit nicht-null Exit-Code.

**Betroffene Dateien/Pfade:** neuer CLI-Einstiegspunkt unter `src/`, `src/storage/sqlite_store.py`, neue CLI-Tests unter `tests/`, `README.md`  
**Abhängigkeiten:** T05, T06  
**Ausführung:** Sequentiell

### T08 - Verwaltungs-CLI für Empfänger bereitstellen

**Workstream:** WS2  
**Kategorie:** Luna  
**Beschreibung:** Die CLI-Unterbefehle zum Hinzufügen, Entfernen und
Auflisten von Reiseempfängern ergänzen.

**Acceptance Criteria:**

- Empfänger können einer bestehenden Reise hinzugefügt, entfernt und je Reise aufgelistet werden.
- Doppelte Empfänger, ungültige E-Mail-Adressen und unbekannte Reisen liefern nicht-null Exit-Codes.
- Die Ausgabe folgt dem in T07 festgelegten Text- und JSON-Vertrag.

**Betroffene Dateien/Pfade:** neuer CLI-Einstiegspunkt unter `src/`, `src/storage/sqlite_store.py`, neue CLI-Tests unter `tests/`, `README.md`  
**Abhängigkeiten:** T05, T06, T07  
**Ausführung:** Sequentiell

### T09 - Reisezeitraum in Movacar-Requests integrieren

**Workstream:** WS3  
**Kategorie:** Luna  
**Beschreibung:** Den Movacar-Client so erweitern, dass er den Pick-up-Zeitraum
einer Reise in die bestätigten API-Start- und Endparameter übersetzt. Bestehende
Retries gelten weiterhin für jeden einzelnen Reise-Request.

**Acceptance Criteria:**

- Der Client akzeptiert einen Reisezeitraum statt eines parameterlosen globalen Abrufs.
- Der Request enthält `locale=en`, `pickupDateFrom` und `pickupDateTo`.
- `pickupDateFrom` und `pickupDateTo` verwenden das Format `YYYY-MM-DD`.
- Transport- und Antwortfehler bleiben spezifisch unterscheidbar.
- Retry-Verhalten wird pro Reise-Request ausgeführt.

**Betroffene Dateien/Pfade:** `src/api/api_client.py`, `tests/test_api_client.py`, `tests/test_offer_parser.py`  
**Abhängigkeiten:** Keine  
**Ausführung:** Parallelisierbar

### T10 - Distanzdienst und Distanzstufen bereitstellen

**Workstream:** WS3  
**Kategorie:** Luna  
**Beschreibung:** Einen reinen Distanzdienst für die Haversine-Berechnung und
die Klassifikation der verbindlichen Distanzstufen bereitstellen.

**Acceptance Criteria:**

- Die Distanz wird in Kilometern mittels Haversine aus Reise- und Angebotskoordinaten bestimmt.
- Sortierung und Schwellen verwenden den ungerundeten Wert.
- Die Darstellung rundet ausschließlich auf eine Nachkommastelle.
- Die vier Stufen rot, orange, gelb und neutral folgen exakt den Plan-Schwellen.

**Betroffene Dateien/Pfade:** neue Distanzkomponente unter `src/`, neue Distanztests unter `tests/`  
**Abhängigkeiten:** T01  
**Ausführung:** Parallelisierbar

### T11 - Reisebezogene Angebots-Synchronisierung etablieren

**Workstream:** WS3  
**Kategorie:** Sol  
**Beschreibung:** Nach einer vollständig erfolgreichen Parser-Antwort globale
Angebote upserten, Reise-Angebot-Zuordnungen erzeugen oder aktualisieren und
die Distanz je Reise atomar speichern.

**Acceptance Criteria:**

- Angebote bleiben global über die Movacar-ID eindeutig.
- Dasselbe Angebot kann für mehrere Reisen eigene Zuordnungen und unabhängige Neuheit besitzen.
- Neue Zuordnungen werden auch für global bereits bekannte Angebote als versandpflichtig geführt.
- Upsert, Zuordnung, Distanzberechnung und Folgeänderungen einer Reise sind atomar.

**Betroffene Dateien/Pfade:** `src/storage/sqlite_store.py`, neue Synchronisierungskomponente unter `src/`, neue Synchronisierungstests unter `tests/`  
**Abhängigkeiten:** T03, T04, T10  
**Ausführung:** Sequentiell

### T12 - Reisebezogenen Verfügbarkeitsabgleich absichern

**Workstream:** WS3  
**Kategorie:** Terra  
**Beschreibung:** Nach einem erfolgreichen vollständigen Reise-Poll die nicht
gelieferten Zuordnungen genau dieser Reise als nicht verfügbar markieren; bei
HTTP-, API- oder Parserfehlern darf sich deren Zustand nicht ändern.

**Acceptance Criteria:**

- Der Abgleich akzeptiert explizit Reise-ID und vollständige Ergebnis-ID-Menge.
- Nur Zuordnungen der erfolgreichen Reise werden als nicht verfügbar markiert.
- Fehlerhafte oder unvollständige Antworten ändern weder Verfügbarkeit noch Versandstatus.
- Der Zeitpunkt „nicht verfügbar seit“ wird für die Retention erfasst.

**Betroffene Dateien/Pfade:** `src/storage/sqlite_store.py`, neue Synchronisierungskomponente unter `src/`, `tests/test_sqlite_store_ops.py`, neue Synchronisierungstests unter `tests/`  
**Abhängigkeiten:** T11  
**Ausführung:** Sequentiell

### T13 - Versandstatus und Zuordnungs-Retention verwalten

**Workstream:** WS3  
**Kategorie:** Terra  
**Beschreibung:** Den Versandstatus nur nach erfolgreicher SMTP-Übergabe
persistieren und nicht verfügbare Reise-Angebot-Zuordnungen nach 14 Tagen
bereinigen, ohne noch referenzierte globale Angebote zu löschen.

**Acceptance Criteria:**

- Nur in einer erfolgreich gesendeten Nachricht enthaltene neue Zuordnungen werden als versendet markiert.
- Ein SMTP-Fehler lässt die betreffenden Zuordnungen erneut zustellbar.
- Nicht verfügbare Zuordnungen werden nach 14 Tagen entfernt.
- Ein globales Angebot wird nur entfernt, wenn keine Reisezuordnung mehr darauf verweist.

**Betroffene Dateien/Pfade:** `src/storage/sqlite_store.py`, `tests/test_sqlite_store_retention.py`, neue Versandstatus-Tests unter `tests/`  
**Abhängigkeiten:** T03, T12  
**Ausführung:** Parallelisierbar

### T14 - Reise-Mailansicht und Angebotsabfragen bereitstellen

**Workstream:** WS4  
**Kategorie:** Terra  
**Beschreibung:** Die Abfragen und die vorbereitete Mailansicht für neue,
verfügbare und unversendete Reise-Angebot-Zuordnungen bereitstellen.

**Acceptance Criteria:**

- Neue verfügbare unversendete und alle verfügbaren Angebote werden ausschließlich für eine Reise abgefragt.
- Beide Mengen werden aufsteigend nach ungerundeter Distanz sortiert.
- Die Ansicht enthält Reiseinformationen, explizite Empfänger, Distanzwerte und Distanzstufen.
- Neue Angebote können in beiden Mailabschnitten erscheinen.

**Betroffene Dateien/Pfade:** `src/storage/sqlite_store.py`, neue Benachrichtigungskomponente unter `src/`, neue Mailansichtstests unter `tests/`  
**Abhängigkeiten:** T01, T03, T11  
**Ausführung:** Sequentiell

### T15 - Sofortbenachrichtigungen reisebasiert versenden

**Workstream:** WS4  
**Kategorie:** Sol  
**Beschreibung:** Nach erfolgreicher Reise-Synchronisierung eine
Sofortbenachrichtigung mit neuen Angeboten zuerst und allen verfügbaren
Angeboten anschließend ausschließlich an die Empfänger dieser Reise senden.

**Acceptance Criteria:**

- Sofortmails verwenden die in T14 bereitgestellte Reise-Mailansicht.
- Es gibt keinen globalen Empfänger-Fallback.
- Versandstatus wird ausschließlich bei erfolgreicher SMTP-Übergabe aktualisiert.
- Ein SMTP-Fehler lässt einen erneuten Zustellversuch im nächsten Durchlauf zu.

**Betroffene Dateien/Pfade:** neue Benachrichtigungskomponente unter `src/`, `src/mailer/smtp_mailer.py`, `src/storage/sqlite_store.py`, `tests/test_smtp_mailer.py`, neue Benachrichtigungstests unter `tests/`  
**Abhängigkeiten:** T13, T14, T17  
**Ausführung:** Sequentiell

### T16 - Reisebezogene Übersichten mit Slot-Persistenz versenden

**Workstream:** WS4  
**Kategorie:** Terra  
**Beschreibung:** Die bisherigen Übersichtszeitpunkte 09:00 und 21:00 in
`Europe/Berlin` pro Reise mit persistentem, erst nach erfolgreichem Versand
gesetztem Slot-Zustand umsetzen.

**Acceptance Criteria:**

- Erreichte Slots werden in `Europe/Berlin` bestimmt.
- Eine Reise erhält höchstens eine erfolgreiche Übersicht je lokalem Datum und Slot.
- Slot-Zustand wird erst nach erfolgreicher SMTP-Übergabe persistiert.
- Fehlgeschlagene Slots bleiben im nächsten Durchlauf wiederholbar.

**Betroffene Dateien/Pfade:** `src/loop/poll_loop.py`, `src/config/timezone.py`, `src/storage/sqlite_store.py`, neue Zeitplan- oder Benachrichtigungskomponente unter `src/`, neue Übersichtstests unter `tests/`  
**Abhängigkeiten:** T03, T14, T17  
**Ausführung:** Sequentiell

### T17 - Mail-Templates auf Reiseinformationen und Distanz umstellen

**Workstream:** WS4  
**Kategorie:** Luna  
**Beschreibung:** Beide Mailtypen auf die vorbereitete Reise-Mailansicht
umstellen: Reiseinformationen, neue Angebote zuerst, alle verfügbaren Angebote
danach sowie die drei Distanzdarstellungen.

**Acceptance Criteria:**

- Sofortmails listen neue Angebote vor dem vollständigen Verfügbarkeitsabschnitt.
- Der vollständige Abschnitt enthält neue Angebote erneut und ist distanzsortiert.
- Reisenamen und weitere Reiseinformationen sind sichtbar.
- Unter 100 km ist rot, 100 bis unter 250 km orange, 250 bis unter 500 km gelb und ab 500 km neutral dargestellt.
- Übersichten enthalten keine Versandentscheidungs-Kennzeichnung, aber Reise- und Distanzinformationen.

**Betroffene Dateien/Pfade:** `src/mailer/templates.py`, `tests/test_mail_templates.py`  
**Abhängigkeiten:** T01, T10  
**Ausführung:** Parallelisierbar

### T18 - SMTP- und Settings-Vertrag bereinigen

**Workstream:** WS5  
**Kategorie:** Luna  
**Beschreibung:** Globale fachliche Empfänger und die alte
Deutschland-Bounding-Box aus dem aktiven Settings-Vertrag entfernen. Gmail SMTP
nutzt Verbindung, Absender und ein App-Passwort; vorhandene Legacy-Werte werden
sichtbar protokolliert.

**Acceptance Criteria:**

- `SmtpSettings` enthält keine fachlichen Empfänger.
- `SMTP_TO` und `DE_BBOX_*` werden nicht mehr fachlich gelesen und bewirken keinen Versand oder Filter.
- Vorhandene Legacy-Werte erzeugen sichtbare Hinweise ohne Startfehler.
- Das Gmail-App-Passwort wird ausschließlich über `SMTP_PASSWORD` aus lokaler, nicht versionierter Konfiguration bezogen und nie im Quellcode hinterlegt.

**Betroffene Dateien/Pfade:** `src/config/settings.py`, `src/mailer/smtp_mailer.py`, `src/logging/logger.py`, `tests/test_settings.py`, `tests/test_smtp_mailer.py`, `tests/test_environment_setup.py`  
**Abhängigkeiten:** Keine  
**Ausführung:** Parallelisierbar

### T19 - Polling-Loop zum fehlerisolierten Reise-Orchestrator umbauen

**Workstream:** WS5  
**Kategorie:** Sol  
**Beschreibung:** Den globalen Polling-Ablauf durch einen sequenziellen
Reise-Orchestrator ersetzen, der Reisen lädt, pro Reise abfragt,
synchronisiert und benachrichtigt sowie Fehler isoliert protokolliert.

**Acceptance Criteria:**

- Alle gespeicherten Reisen werden je Zyklus sequenziell verarbeitet.
- Ein Fehler einer Reise wird mit Reise-ID und -Name protokolliert und verhindert nicht die Verarbeitung weiterer Reisen.
- Ohne Reisen erfolgen weder HTTP- noch SMTP-Aufrufe; der Leerlauf wird protokolliert.
- Das normale Poll-Intervall bleibt auch im Leerlauf erhalten.

**Betroffene Dateien/Pfade:** `src/loop/poll_loop.py`, `src/logging/logger.py`, `tests/test_poll_loop.py`, `tests/test_logger_contract.py`, `tests/test_end_to_end_flow.py`  
**Abhängigkeiten:** T05, T09, T11, T12, T15, T16  
**Ausführung:** Sequentiell

### T20 - Alte globale Matching- und Highlightpfade entfernen

**Workstream:** WS5  
**Kategorie:** Terra  
**Beschreibung:** Den globalen Delta-, Deutschland-Bounding-Box- und
Dauerhighlightpfad kontrolliert aus dem Produktionsfluss und den aktiven
Verträgen entfernen.

**Acceptance Criteria:**

- Der Produktionsablauf verwendet kein globales `OfferDelta`.
- `ClassifiedOffer`, `offer_matcher` und `geo_rules` tragen keine aktive Produktionsverantwortung mehr.
- Die alte Deutschland-/Mindestdauer-Regel beeinflusst keine Bewertung oder Maildarstellung.
- Es bleibt kein paralleler Legacy-Polling- oder Empfänger-Fallbackpfad.

**Betroffene Dateien/Pfade:** `src/models/offer.py`, `src/matcher/offer_matcher.py`, `src/matcher/geo_rules.py`, `src/loop/poll_loop.py`, `src/config/settings.py`, `tests/test_offer_matcher.py`, `tests/test_geo_rules.py`  
**Abhängigkeiten:** T10, T17, T18, T19  
**Ausführung:** Sequentiell

### T21 - Bestehende Tests auf Reiseverträge umstellen

**Workstream:** WS6  
**Kategorie:** Terra  
**Beschreibung:** Tests für ausschließlich entfallene globale Fachlichkeit
entfernen oder ersetzen. Bestehende Parser-, Retry-, Zeitzonen-, SMTP-Transport-
und Logging-Grundverträge bleiben erhalten und werden um den Reisekontext
ergänzt.

**Acceptance Criteria:**

- Tests konservieren kein globales Delta, keine globalen Empfänger, keine globale Übersicht und keine Bounding-Box-Fachlichkeit.
- Parser-, Retry-, Zeitzonen-, SMTP-Transport- und Logging-Grundverträge bleiben abgedeckt.
- Betroffene Tests prüfen die neuen reisespezifischen Schnittstellen.

**Betroffene Dateien/Pfade:** `tests/test_offer_matcher.py`, `tests/test_geo_rules.py`, `tests/test_poll_loop.py`, `tests/test_settings.py`, `tests/test_mail_templates.py`, `tests/test_smtp_mailer.py`  
**Abhängigkeiten:** T09, T17, T18, T19, T20  
**Ausführung:** Sequentiell

### T22 - Unit-Tests für neue Reiseverträge ergänzen

**Workstream:** WS6  
**Kategorie:** Terra  
**Beschreibung:** Die im Plan geforderten Unit-Tests für Migration, Verwaltung,
Distanz, Zuordnung, Verfügbarkeit, Versand, Retention, API-Requestbildung,
Templates, Übersichtsslots und Legacy-Hinweise ergänzen.

**Acceptance Criteria:**

- Alle in Abschnitt 10.2 von `plan_v2.1.md` aufgezählten Mindestfälle sind automatisiert abgedeckt.
- Tests verwenden keine echten externen Netzwerkzugriffe.
- Jeder neue oder geänderte Fachvertrag besitzt mindestens einen passenden Unit-Test.

**Betroffene Dateien/Pfade:** `tests/test_sqlite_schema.py`, `tests/test_sqlite_store_ops.py`, `tests/test_sqlite_store_retention.py`, `tests/test_api_client.py`, `tests/test_mail_templates.py`, `tests/test_settings.py`, `tests/test_smtp_mailer.py`, neue Tests unter `tests/`  
**Abhängigkeiten:** T04, T08, T09, T10, T12, T13, T15, T16, T18, T20  
**Ausführung:** Sequentiell

### T23 - Hermetischen Reise-E2E-Test erstellen

**Workstream:** WS6  
**Kategorie:** Sol  
**Beschreibung:** Einen End-to-End-Test mit isolierter SQLite-Datenbank sowie
Movacar- und SMTP-Doubles bereitstellen, der den vollständigen reisebasierten
Ablauf abdeckt.

**Acceptance Criteria:**

- Der Test deckt mehrere Reisen, reisespezifische Requestparameter und ein gemeinsames Angebot mit unabhängigen Erstbenachrichtigungen ab.
- Sofortmail und Übersicht prüfen Distanzsortierung, beide Highlightstufen und Reiseinformationen.
- Eine fehlerhafte Reise hält eine andere erfolgreiche Reise nicht auf.
- Verfügbarkeit, Retention, SMTP-Wiederholung und Leerlauf ohne externe Aufrufe sind abgedeckt.
- Der Test kontaktiert weder Gmail noch Movacar noch OpenStreetMap oder einen anderen externen Dienst.

**Betroffene Dateien/Pfade:** `tests/test_end_to_end_flow.py`, Test-Doubles oder Fixtures unter `tests/`, `src/main.py`, `src/loop/poll_loop.py`  
**Abhängigkeiten:** T07, T08, T13, T15, T16, T19, T22  
**Ausführung:** Sequentiell

### T24 - Betriebs- und Nutzungsdokumentation aktualisieren

**Workstream:** WS6  
**Kategorie:** Luna  
**Beschreibung:** Die Projektdokumentation auf Reiseverwaltung, CLI,
Koordinatenpflicht, Migration, Gmail-App-Passwort, Legacy-Hinweise, Leerlauf
und reisebezogenes Mailverhalten aktualisieren.

**Acceptance Criteria:**

- Die Dokumentation beschreibt Einrichtung und sichere lokale Konfiguration ohne Secrets im Repository.
- Reise- und Empfänger-CLI sind mit Pflichtangaben und Ausgabeformen dokumentiert.
- Pflichtkoordinaten und die fehlende Laufzeit-Geocodierung sind klar beschrieben.
- Migrationsverhalten, Leerlauf ohne Reisen, reisebezogene Empfänger und Distanzdarstellung sind dokumentiert.

**Betroffene Dateien/Pfade:** `README.md`, `.env.example` falls vorhanden, `SDD/tasks_v2.1.md`  
**Abhängigkeiten:** T07, T08, T18, T19  
**Ausführung:** Parallelisierbar

## 6. Abhängigkeits- und Ausführungsregel

„Parallelisierbar“ bedeutet, dass die Aufgabe nach Erfüllung ihrer angegebenen
Abhängigkeiten unabhängig von anderen parallelisierbaren Aufgaben umgesetzt
werden kann. „Sequentiell“ kennzeichnet Aufgaben, deren Änderungsscope oder
fachlicher Zustand eine geordnete Umsetzung erfordert.
