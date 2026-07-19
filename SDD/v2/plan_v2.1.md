# Plan v2.1: Reise-basierte Zielarchitektur und Systemintegration

## 1. Status, Ziel und Geltungsbereich

Dieser Plan ersetzt `plan_v2.0.md` als maßgeblichen Planungsstand für
`spec_v2.0.md`. Er beschreibt das **Zielsystem als Ganzes**, einschließlich
der Umgestaltung bestehender Komponenten. `plan_v2.0.md` bleibt als
nachvollziehbarer Vorläufer erhalten, ist jedoch nicht die Grundlage der
TASK-Phase.

Das Zielsystem verwaltet mehrere persistierte Reisen. Für jede Reise fragt es
die Movacar-API in deren Pick-up-Zeitraum ab, bewertet Angebote relativ zur
Reise-Startstadt und versendet neue Angebote sowie geplante Übersichten nur an
Empfänger dieser Reise.

Nicht Gegenstand dieses Dokuments sind Implementierungsaufgaben oder Code.

## 2. Verbindliche Entscheidungen

| Thema | Entscheidung |
|---|---|
| Reiseort | Jede Reise speichert Startstadt, Latitude und Longitude verpflichtend. Eine Laufzeit-Geocodierung ist nicht Teil des Standardpfads. |
| Angebotsspeicherung | Angebote sind global über ihre Movacar-ID eindeutig. Ihr fachlicher Zustand wird pro Reise geführt. |
| Mehrfachtreffer | Dasselbe Angebot kann mehreren Reisen zugeordnet und für jede Reise eigenständig als neu versendet werden. |
| Verfügbarkeit | Nach erfolgreichem vollständigem Poll einer Reise werden deren nicht gelieferten Zuordnungen als nicht verfügbar markiert. Ein Poll-Fehler ändert keine Verfügbarkeit. |
| Distanz | Haversine-Formel; Kilometer; Darstellung mit einer Nachkommastelle. Die ungerundete Distanz bestimmt Sortierung und Schwellen. |
| Distanzstufen | Unter 100 km: rote Hervorhebung. 100 km bis unter 250 km: orange Hervorhebung. 250 km bis unter 500 km: gelbe Hervorhebung. Ab 500 km: neutral. |
| Altes Highlighting | Die bisherige Deutschland-/Mindestdauer-Regel wird vollständig entfernt und nicht parallel fortgeführt. |
| Übersichten | Die bisherigen Übersichten um 09:00 und 21:00 Uhr bleiben erhalten, werden aber pro Reise und nur an deren Empfänger versendet. |
| Polling | Reisen werden innerhalb eines Zyklus sequenziell und fehlerisoliert verarbeitet; bestehende HTTP-Retries gelten pro Reise. |
| Leerer Bestand | Ohne Reisen läuft der Dienst weiter, führt aber keine API- oder SMTP-Aufrufe aus und protokolliert den Leerlauf. |
| Versand | Separates Gmail-Konto; SMTP mit App-Passwort; Secrets nur in Umgebungsvariablen oder lokaler, nicht versionierter Konfiguration. |
| CLI | Unterbefehle für Reise- und Empfängeroperationen; lesbare Ausgabe, optional JSON, nicht-null Exit-Code bei Fehlern. |
| Löschung | Das Löschen einer Reise löscht Reise, Empfänger und Reise-Angebot-Zuordnungen transaktional; globale Angebote bleiben erhalten. |
| Retention | Nicht verfügbare Reise-Angebot-Zuordnungen werden nach 14 Tagen bereinigt. Globale Angebote werden erst gelöscht, wenn keine Zuordnung mehr auf sie verweist. |
| Testausführung | Unit-Tests für jede neue oder geänderte Funktion sowie ein hermetischer E2E-Test mit Test-Doubles. |

## 3. Bestandsarchitektur und Änderungsmatrix

| Bestehende Komponente | Aktuelles Verhalten | Zielverhalten und Maßnahme |
|---|---|---|
| `src/main.py` | Lädt globale Settings, initialisiert SQLite und startet den Endlos-Poller. | Bleibt Einstiegspunkt. Initialisiert die versionierte Migration und startet den reisebasierten Poller. |
| `src/loop/poll_loop.py` | Eine globale API-Abfrage, ein globaler Angebotsdelta und globale Tagesübersichten. | Wird zum Reise-Orchestrator refaktoriert: Laden aller Reisen, sequenzielle fehlerisolierte Verarbeitung und Übersichten pro Reise. |
| `src/api/api_client.py` | Ruft `API_URL` ohne Reiseparameter ab; HTTP-Retries sind global. | Bleibt HTTP-Grenze, nimmt aber einen Reisezeitraum entgegen und bildet daraus die API-Start-/Endparameter. Retries bleiben je Request. |
| `src/parser/offer_parser.py` | Erzeugt vollständige `Offer`-Objekte mit Stationskoordinaten. | Wird beibehalten. Die Vollständigkeits- und All-or-nothing-Garantie bleibt Voraussetzung für einen erfolgreichen Reise-Poll. |
| `src/models/offer.py` | `Offer` und `ClassifiedOffer` enthalten globalen Neuheits- und booleschen Highlightstatus. | `Offer` bleibt globale API-Repräsentation. Der reisespezifische Zustand, Distanz und Highlightstufe werden aus `ClassifiedOffer` herausgelöst. |
| `src/matcher/offer_matcher.py` | Vergleicht gegen globale IDs und wendet Deutschland-/Dauer-Highlighting an. | Wird ersetzt bzw. in reisespezifische Zuordnungs- und Distanzdienste überführt. Kein globaler Delta- oder Highlightvertrag bleibt bestehen. |
| `src/matcher/geo_rules.py` | Prüft eine konfigurierbare Deutschland-Bounding-Box. | Wird aus dem Laufzeitpfad und der aktiven Konfiguration entfernt, weil die fachliche Regel entfällt. |
| `src/storage/sqlite_store.py` | Besitzt eine globale `offers`-Tabelle, Soft-Delete und 14-Tage-Purge. | Wird zum Persistenzmodul für Migrationen, Reisen, Empfänger, globale Angebote und Reise-Angebot-Zuordnungen refaktoriert. Retention wird zuordnungsbezogen. |
| `src/mailer/templates.py` | Rendert globale neue/bestehende Angebote und eine globale Übersicht. | Wird auf eine Reise-Mail-Ansicht umgestellt: Reiseinformationen, neue Angebote zuerst, danach alle aktuellen Angebote, Distanz und Distanzstufen. |
| `src/mailer/smtp_mailer.py` | Adressiert die globale `SMTP_TO`-Empfängerliste. | Bleibt SMTP-Grenze, erhält Empfänger explizit aus der Reise-Mail-Ansicht statt aus globalen Settings. |
| `src/config/settings.py` | Enthält globale Empfänger und Deutschland-Bounding-Box. | Entfernt diese aktiven Verträge. Behält API-, Polling-, SQLite-, SMTP-, Timeout- und Logging-Einstellungen. |
| `src/logging/logger.py` | Konfiguriert Konsolen- und optionales Dateilogging. | Bleibt bestehen; Polling-Logs erhalten Reise-ID/-Name und Ergebnis je Reise. |
| `README.md` | Dokumentiert globale Empfänger, globale Abfrage und altes Highlighting. | Dokumentiert Reiseverwaltung, neue Konfiguration, Gmail-App-Passwort, CLI, Migration, Leerlauf ohne Reisen und Mailverhalten. |
| Bestehende Tests | Prüfen globale Deltas, Bounding-Box-Regeln, globale Empfänger und globale Zusammenfassungen. | Werden an den Zielvertrag angepasst; entfernte Verträge werden nicht als Legacy-Verhalten konserviert. |

## 4. Zielarchitektur

### 4.1 Komponenten und Verantwortlichkeiten

| Zielkomponente | Verantwortung |
|---|---|
| Laufzeit-Einstieg | Settings laden, Logging konfigurieren, Datenbank migrieren und Dauerbetrieb starten. |
| Reiseverwaltung | Reisen und Empfänger validieren sowie atomar anlegen, löschen, hinzufügen und entfernen. |
| Verwaltungs-CLI | Unterbefehle, Ein-/Ausgabeformat, Fehlertexte und Prozess-Exit-Codes. |
| Reise-Repository | Reisen und Empfänger lesen und verwalten. |
| Angebots-Repository | Globale Angebote per Movacar-ID speichern und aktualisieren. |
| Zuordnungs-Repository | Reise-Angebot-Zuordnungen, Verfügbarkeit, Distanz, Neuheits- und Versandstatus verwalten. |
| Movacar-Client | HTTP-Request für einen Reisezeitraum bauen, wiederholen und Antwort transportieren. |
| Parser | API-Antwort vollständig zu validierten globalen Angeboten normalisieren. |
| Reise-Synchronisierer | Angebote upserten, Zuordnungen je Reise aktualisieren und nach erfolgreicher Antwort Verfügbarkeit abgleichen. |
| Distanzdienst | Luftliniendistanz sowie Highlightstufe berechnen. |
| Benachrichtigungsservice | Neue und verfügbare Angebote einer Reise abfragen, sortieren, Template-Ansicht erstellen, senden und Versandstatus persistieren. |
| E-Mail-Composer | HTML-Inhalt für Sofortbenachrichtigungen und planmäßige Reiseübersichten erzeugen. |
| SMTP-Mailer | HTML-Nachrichten über Gmail SMTP an explizit übergebene Empfänger senden. |
| Zeitplanlogik | Bestimmt die lokalen Übersichtsslots 09:00 und 21:00 Uhr und stellt sicher, dass je Reise höchstens einmal pro Slot versendet wird. |

### 4.2 Abhängigkeitsrichtung

Die Laufzeit-Orchestrierung hängt von Repository- und Adapter-Schnittstellen
ab. Parser und Distanzdienst sind reine Fachlogik. Templates erhalten
fertige Reise-Mail-Ansichten und greifen nicht auf SQLite, Settings oder
externe Dienste zu. Der SMTP-Mailer kennt keine Reise- oder Angebotsdaten.

## 5. Datenmodell, Zustände und Migration

### 5.1 Zieltabellen

| Tabelle | Schlüssel und Beziehungen | Inhalt |
|---|---|---|
| `trips` | Primärschlüssel `trip_id` | Name, Pick-up-Beginn, Pick-up-Ende, Startstadt, Latitude, Longitude, Zeitstempel |
| `trip_recipients` | Eindeutig `(trip_id, normalized_email)`; Fremdschlüssel auf `trips` | Empfänger einer Reise |
| `offers` | Movacar-Angebots-ID als global eindeutiger Schlüssel | Normalisierte Angebotsdaten einschließlich Start- und Zielstation, Zeitfenster und zuletzt beobachteter Daten |
| `trip_offers` | Eindeutig `(trip_id, offer_id)`; Fremdschlüssel auf `trips` und `offers` | Distanz, Verfügbarkeit, erstmals/zuletzt gesehen, Nichtverfügbar-seit, Neuheits-/Versandstatus und Versandzeitpunkt |
| Übersichtsslot-Zustand | Eindeutig `(trip_id, local_date, slot_hour)` | Erfolgreich versendete Zusammenfassungs-Slots pro Reise |
| Migrationsmetadaten | Version als Primärschlüssel | Bereits ausgeführte Schemaänderungen |

Die konkrete physische Tabellennamensgebung folgt den bestehenden
SQLite-Konventionen; die genannten Identitäten, Eindeutigkeiten und
Beziehungen sind verbindlich.

### 5.2 Zustandsregeln

- Ein globales Angebot darf ohne Reisezuordnung existieren.
- Eine Reise-Angebot-Zuordnung entsteht, sobald das Angebot erstmals in der
  erfolgreichen Antwort dieser Reise vorkommt.
- Eine neue Zuordnung ist für diese Reise versandpflichtig, auch wenn das
  globale Angebot vor der Zuordnung bereits historisch bekannt war.
- Verfügbarkeit und Versandstatus sind niemals globale Angebotsattribute.
- Nach einer vollständigen erfolgreichen Antwort werden nur Zuordnungen
  **dieser** Reise, deren IDs nicht in der Antwort vorkommen, als nicht
  verfügbar markiert.
- Bei HTTP-, API- oder Parserfehlern wird für diese Reise weder Verfügbarkeit
  noch Versandstatus geändert.
- Nach erfolgreicher SMTP-Übergabe werden nur die in der Nachricht
  enthaltenen neuen Zuordnungen als versendet markiert.
- Ein SMTP-Fehler lässt die betreffenden Zuordnungen erneut zustellbar.
- Beim Löschen einer Reise entfernen Fremdschlüssel-Kaskaden oder eine
  äquivalente Transaktion deren Empfänger, Zuordnungen und Übersichtsslot-
  Zustände. Globale Angebote bleiben bestehen.

### 5.3 Historische Daten und Retention

Die vorhandene globale `offers`-Tabelle wird migrationssicher in die globale
Angebotshistorie überführt. Bestandsangebote erhalten keine künstliche
Reisezuordnung. Wenn sie nach der Migration in einer Reiseantwort erscheinen,
entsteht eine neue Zuordnung und damit eine reisespezifische
Erstbenachrichtigung.

Die bisherige 14-Tage-Soft-Delete-/Purge-Strategie wird auf nicht verfügbare
`trip_offers` übertragen. Beim Purge werden abgelaufene Zuordnungen entfernt.
Ein globales Angebot darf nur entfernt werden, wenn keine verbleibende
Reise-Angebot-Zuordnung auf es verweist. Damit bleibt die Historie erhalten,
ohne dauerhaft verwaiste globale Datensätze aufzubauen.

### 5.4 Migrationsvertrag

Migrationen sind versioniert, additiv, transaktional und idempotent. Eine
bereits migrierte Datenbank darf bei erneutem Start nicht verändert werden.
Eine unterbrochene Migration darf nicht zu einem teilweise aktivierten
Schema führen. Der Dienst startet das Polling erst nach erfolgreicher
Migration.

## 6. End-to-End-Datenflüsse

### 6.1 Verwaltung per CLI

1. Die CLI verarbeitet Unterbefehle für Reiseanlage/-löschung und
   Empfängeranlage/-löschung.
2. Die Reiseverwaltung validiert Name, Pick-up-Zeitraum, Startstadt,
   Koordinaten und E-Mail-Adresse.
3. Das Repository schreibt die Änderung transaktional.
4. Die CLI gibt eine lesbare Erfolgsmeldung oder bei angefordertem JSON eine
   strukturierte Antwort aus.
5. Ungültige Eingaben, unbekannte Reisen, doppelte Empfänger und
   Persistenzfehler enden mit nachvollziehbarer Meldung und nicht-null
   Exit-Code.

### 6.2 Dienststart und Leerlauf

1. Der Einstieg lädt gültige Laufzeitkonfiguration und richtet Logging ein.
2. Das Persistenzmodul führt ausstehende Migrationen aus.
3. Der Poller lädt Reisen.
4. Gibt es keine Reisen, protokolliert er den Leerlauf, wartet das normale
   Poll-Intervall und löst weder HTTP- noch SMTP-Zugriffe aus.

### 6.3 Reisebasierter Polling-Zyklus

1. Der Orchestrator lädt alle Reisen und verarbeitet sie sequenziell.
2. Für jede Reise baut der Movacar-Client eine Anfrage aus deren
   Pick-up-Beginn und -Ende.
3. Der Client führt die bestehenden Retry-Delays pro Reise-Request aus.
4. Der Parser validiert die vollständige Antwort und erzeugt globale
   `Offer`-Objekte mit Startkoordinaten.
5. Der Reise-Synchronisierer führt den globalen Angebots-Upsert, die
   Reisezuordnung, die Distanzberechnung und den Verfügbarkeitsabgleich
   atomar für diese Reise aus.
6. Ein Fehler dieser Reise wird mit Reise-ID/-Name protokolliert; der
   Orchestrator fährt mit der nächsten Reise fort.

### 6.4 Sofortbenachrichtigung

1. Nach erfolgreicher Synchronisierung liest der Benachrichtigungsservice
   die neuen verfügbaren unversendeten Zuordnungen und alle verfügbaren
   Zuordnungen der Reise.
2. Er sortiert beide Mengen aufsteigend nach ungerundeter Distanz.
3. Der Composer erzeugt eine Reise-Mail mit Reiseinformationen, neuen
   Angeboten als erstem Abschnitt und allen aktuell verfügbaren Angeboten
   als zweitem Abschnitt. Neue Angebote erscheinen damit in beiden
   Abschnitten.
4. Der SMTP-Mailer sendet ausschließlich an die Empfänger dieser Reise.
5. Erst bei erfolgreichem Versand werden die neuen Zuordnungen als versendet
   markiert. Ein Fehler verändert diesen Status nicht.

### 6.5 Geplante Reiseübersicht

1. Die Zeitplanlogik bestimmt in `Europe/Berlin` die erreichten Slots 09:00
   und 21:00 Uhr.
2. Für jede erfolgreich verarbeitete Reise prüft sie den persistenten
   Übersichtsslot-Zustand.
3. Ist ein Slot noch nicht versendet, lädt sie die aktuell verfügbaren
   Zuordnungen dieser Reise, sortiert sie nach Distanz und sendet eine
   reisespezifische Übersicht an deren Empfänger.
4. Der Slot wird erst nach erfolgreichem SMTP-Versand persistiert; ein
   fehlgeschlagener Slot bleibt im nächsten Durchlauf wiederholbar.

## 7. Schnittstellen und Vertragsänderungen

### 7.1 Movacar-Client

Der Client erhält neben allgemeinen HTTP-Settings einen Reisezeitraum und
übersetzt ihn in die von der Movacar-kompatiblen API erwarteten Start- und
Endparameter. Er liefert entweder eine valide Rohantwort oder einen
spezifischen Transport-/Antwortfehler. Die genaue Bezeichnung und Kodierung
dieser Query-Parameter muss gegen den tatsächlichen API-Vertrag bestätigt
werden; sie darf nicht aus bisherigen parameterlosen Requests abgeleitet
werden.

### 7.2 Parser und Angebotsmodell

Der Parser behält seinen vollständigen Validierungsvertrag: Ein unvollständig
auflösbares Angebot macht die gesamte Antwort für die Reise ungültig. Das
globale `Offer` bleibt unveränderlich und enthält keine Reise- oder
Versanddaten. Eine getrennte Reise-Angebot-Ansicht trägt:

- Reiseidentität und Angebot,
- ungerundete und darstellbare Distanz,
- Verfügbarkeits- und Neuheitsstatus,
- Highlightstufe statt booleschem Althighlight,
- Versandstatus.

### 7.3 Distanzdienst

Der Distanzdienst akzeptiert die Koordinaten von Reise und Angebotsstart. Er
berechnet Haversine-Kilometer, speichert/ordnet nach dem ungerundeten Wert und
rundet ausschließlich zur Darstellung auf eine Nachkommastelle. Seine
Klassifikation ist: `<100`, `>=100 und <250`, `>=250 und <500`, `>=500`.

### 7.4 Persistenz

Repositorymethoden arbeiten im Reisekontext, wo Zustand fachlich
reisespezifisch ist. Insbesondere dürfen Abfragen nach bekannten, neuen,
verfügbaren, entfernten oder versendeten Angeboten keine globale
ID-Menge ohne Reise-ID verwenden. Der Verfügbarkeitsabgleich nimmt explizit
die Reise-ID und die vollständige erfolgreiche Ergebnis-ID-Menge entgegen.

### 7.5 E-Mail-Composer und SMTP

Der Composer erhält eine vorbereitete Reise-Mail-Ansicht. Diese umfasst
Reiseinformationen, Empfänger, neue Angebote, alle aktuellen Angebote,
Distanzwerte und Highlightstufen. Der SMTP-Mailer erhält Empfänger explizit
pro Sendung; `SmtpSettings` enthält künftig Verbindung und Absender, nicht
mehr fachliche Empfänger.

Sofortbenachrichtigung und Übersicht verwenden denselben reisebezogenen
Angebots- und Distanzvertrag. Die Übersicht enthält keine neue/alt-
Kennzeichnung als Versandentscheidung, aber Reiseinformationen und die
distanzsortierten aktuellen Angebote.

### 7.6 Konfiguration

| Konfiguration | Zielvertrag |
|---|---|
| `API_URL`, `POLL_INTERVAL_MINUTES`, `SQLITE_PATH`, `HTTP_TIMEOUT_SECONDS`, `LOG_FILE_PATH` | Bleiben Laufzeitkonfiguration. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS` | Bleiben erforderlich für Gmail SMTP; `SMTP_PASSWORD` ist das App-Passwort. |
| `SMTP_TO` | Wird nicht mehr gelesen. Falls in `.env` vorhanden, wird ein sichtbarer Hinweis protokolliert, der Dienst startet aber weiter. |
| `DE_BBOX_*` | Werden nicht mehr gelesen. Vorhandene Werte erzeugen einen sichtbaren Hinweis, aber keinen Startfehler. |
| Reise- und Empfängerdaten | Liegen ausschließlich in SQLite und nicht in Umgebungsvariablen. |

OpenStreetMap wird wegen verpflichtender Koordinaten nicht in den
Produktivfluss eingebunden. Ein künftig vorhandener Geocoding-Adapter wäre
eine optionale, klar abgegrenzte Erweiterung und darf keine Reiseanlage
blockieren.

## 8. Refactorings und Rückwärtskompatibilität

### 8.1 Gezielte Refactorings

- Der globale `OfferDelta` wird durch reisespezifische Synchronisierungs- und
  Benachrichtigungsresultate ersetzt.
- `ClassifiedOffer` und sein boolesches `is_highlighted` werden nicht
  weitergeführt. Template-Daten verwenden eine explizite Distanzstufe.
- `offer_matcher` und `geo_rules` verlieren ihre Produktionsverantwortung.
  Die alte Deutschland-/Dauer-Logik und ihre Konfiguration werden entfernt.
- Der globale Soft-Delete in `offers` wird durch
  reisespezifische Verfügbarkeits- und Retentionslogik ersetzt.
- Die globale tägliche Übersicht wird aus dem Poll-Ergebnis einer einzelnen
  Abfrage entkoppelt und pro Reise aus persistierten verfügbaren Zuordnungen
  erzeugt.
- Die Absendertransportkonfiguration bleibt zentral; Empfänger werden aus
  dem globalen Settings-Modell entfernt.

### 8.2 Garantien beim Übergang

- Vorhandene SQLite-Angebote bleiben globale historische Daten.
- Sie werden nicht nachträglich einer Reise zugeordnet und lösen deshalb
  keine rückwirkenden Versendungen aus.
- Sie können ab dem ersten passenden Reise-Poll pro Reise neu sein.
- Alte globale Empfänger und Bounding-Box-Werte bewirken nach der Umstellung
  keinen Versand und keine fachliche Bewertung mehr.
- Der Dienst bleibt mit einer vorhandenen Alt-`.env` startbar, sofern alle
  weiterhin erforderlichen Werte gültig sind.
- Es gibt keinen parallelen Legacy-Pollingpfad und keine globale
  Fallback-Empfängerliste.

## 9. Seiteneffekte und Betrieb

| Bereich | Auswirkung und Behandlung |
|---|---|
| API-Last | Ein Zyklus führt einen Request pro Reise aus. Sequentielle Verarbeitung begrenzt Parallelität, verlängert aber die Zyklusdauer bei vielen Reisen. |
| Retry-Latenz | Jeder Reise-Request kann die bestehenden Backoffs auslösen. Fehler werden isoliert, damit nachfolgende Reisen nicht ausfallen. |
| SMTP-Volumen | Neue Angebote und 09:00/21:00-Übersichten werden pro Reise versandt. Empfänger, die mehreren Reisen zugeordnet sind, können mehrere fachlich getrennte Nachrichten erhalten. |
| Zustandskonsistenz | Synchronisierung und Verfügbarkeitsabgleich je Reise erfolgen atomar. Versandstatus folgt erst erfolgreichem SMTP-Versand. |
| Löschen | Das Reise-Löschen unterbindet künftige Requests und Sendungen für die Reise sofort nach erfolgreicher Transaktion. |
| Logging | Jede operative Meldung enthält Reise-ID/-Name, Phase, Ergebniszählungen und Fehlerursache; Secrets und E-Mail-Inhalte werden nicht geloggt. |
| Leerlauf | Keine Reisen bedeutet keine externen Aufrufe; der Dienst bleibt für spätere CLI-Verwaltung aktiv. |
| Gmail-Betrieb | Das separate Konto, Zwei-Faktor-Voraussetzung und App-Passwort sind externe Betriebsabhängigkeiten und müssen dokumentiert werden. |

## 10. Teststrategie und bestehende Testverträge

### 10.1 Zu ersetzende Tests

Tests für globale Empfänger, globales Delta, globale Tagesübersicht,
Deutschland-Bounding-Box und Dauerhighlighting werden auf die neuen
reisespezifischen Verträge umgestellt oder entfernt, wenn sie ausschließlich
entfallene Fachlichkeit prüfen. Parser-, HTTP-Retry-, Zeitzonen-, SMTP-
Transport- und Logging-Grundverträge bleiben als Basis erhalten und werden
für den Reisekontext ergänzt.

### 10.2 Unit-Testumfang

Unit-Tests decken mindestens ab:

- Reise- und Empfängervalidierung sowie CLI-Exit-Codes und JSON-Ausgabe,
- Migrationsidempotenz, Schlüssel, Kaskaden und Übernahme alter Angebote,
- Haversine-Berechnung, Rundung, Sortierung und alle Distanzstufen,
- neue Zuordnungen je Reise bei global bekanntem Angebot,
- Verfügbarkeitsabgleich nur nach erfolgreicher vollständiger Antwort,
- SMTP-Fehler ohne Versandstatusänderung,
- Retention nicht verfügbarer Zuordnungen und Schutz referenzierter Angebote,
- Requestbildung pro Reisezeitraum und Retry je Reise,
- Mailstruktur, Reiseinformationen, Empfängerisolation und beide Mailtypen,
- Übersichtsslot-Persistenz und Wiederholung nach Fehler,
- Ignorieren und sichtbares Protokollieren der Legacy-Settings.

### 10.3 Hermetischer E2E-Test

Der E2E-Test verwendet eine isolierte SQLite-Datenbank sowie Test-Doubles für
Movacar und SMTP; eine Geocoding-Grenze wird nicht produktiv aufgerufen und
benötigt daher keinen echten Dienst. Der Ablauf umfasst mindestens:

1. Anlegen mehrerer Reisen mit unterschiedlichen Zeiträumen, Koordinaten und
   Empfängern.
2. Eine gezielte API-Antwort pro Reise und die Bestätigung reisespezifischer
   Requestparameter.
3. Ein identisches Angebot in mehreren Reisen mit unabhängiger
   Erstbenachrichtigung.
4. Distanzsortierung, beide Highlightstufen und Reiseinformationen in
   Sofortmail und Übersicht.
5. Einen Fehler in einer Reise, während eine andere erfolgreich verarbeitet
   und versendet wird.
6. Entfernen eines Angebots aus nur einer Reiseantwort und anschließende
   Retention.
7. Fehlgeschlagenen SMTP-Versand mit erneutem Versandversuch.
8. Leerlauf ohne Reisen ohne HTTP- oder SMTP-Aufruf.

Kein automatisierter Test kontaktiert Gmail, Movacar, OpenStreetMap oder
einen anderen externen Dienst.

## 11. Annahmen, Risiken und offene Punkte

### 11.1 Annahmen

| Annahme | Auswirkung bei Abweichung |
|---|---|
| Die API besitzt für den Reisezeitraum dokumentierte Start- und Endparameter. | Der API-Adaptervertrag muss vor Implementierung präzisiert werden. |
| Jede API-Antwort enthält eine stabile Angebots-ID und Startkoordinaten. | Deduplizierung und Distanzbewertung benötigen eine explizite Alternativstrategie. |
| SQLite kann die benötigten Fremdschlüssel, Transaktionen und Migrationen bereitstellen. | Der Persistenzplan muss an das tatsächlich verwendete Datenbankzugriffsmuster angepasst werden. |
| Das separate Gmail-Konto kann ein App-Passwort nutzen. | Die Versandauthentifizierung muss vor Produktionsbetrieb neu entschieden werden. |

### 11.2 Risiken

| Risiko | Minderung |
|---|---|
| Viele Reisen erhöhen API-Latenz und Zyklusdauer. | Sequenzielle Fehlerisolation, Laufzeitlogging und Beobachtung der Zyklusdauer. |
| Falsche Reise-Angebot-Zuordnung führt zu Doppel- oder Fehlbenachrichtigungen. | Eindeutiger zusammengesetzter Schlüssel und Tests mit mehrfach passenden Angeboten. |
| Migration beschädigt Bestandsdaten. | Versionierte Transaktionen, Idempotenztests und keine künstliche Reisezuordnung. |
| SMTP-Auslieferung ist nach Übergabe nicht vollständig end-to-end beweisbar. | Status erst nach erfolgreicher SMTP-Antwort setzen; Fehler wiederholbar halten. |
| Alte `.env`-Werte suggerieren weiterhin globale Empfänger. | Sichtbare Legacy-Hinweise, aktualisierte Dokumentation und kein Fallback-Verhalten. |

### 11.3 Vor TASK-Phase zu bestätigen

- Die exakten Query-Parameternamen, das Datumsformat und die
  Zeitzonenkonvention der Movacar-API für den Reisezeitraum.
- Ob der bestehende Datenbankzugriff bereits einen Migrationsmechanismus
  bereitstellt oder ob die versionierte Migration innerhalb der SQLite-Grenze
  eingeführt wird.
- Die verbindlichen Namen der neuen Gmail-bezogenen Konfigurationswerte und
  das Verfahren zur sicheren lokalen Bereitstellung des App-Passworts.

## 12. Explizite Nichtbestandteile

- Neue Produktfunktionen außerhalb von `spec_v2.0.md`.
- Ein globaler Legacy-Polling- oder Empfänger-Fallbackpfad.
- Automatische Laufzeit-Geocodierung als Voraussetzung für Reisen.
- Echte externe Netzwerkaufrufe im automatisierten E2E-Test.
- Aufgabenzerlegung für die Umsetzung; diese gehört zur TASK-Phase.
- Implementierungscode; dieser gehört zur anschließenden Umsetzungsphase.
