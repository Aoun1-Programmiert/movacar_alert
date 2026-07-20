# Plan v3.0: Zusätzlicher Anbieter (Imoova) und anbieterspezifischer Versand

## 1. Status, Ziel und Geltungsbereich

Dieser Plan konkretisiert `spec_v3.0.md`. Es gibt in diesem Zyklus keinen
Vorläuferplan; frühere Pläne (`SDD/v1/`, `SDD/v2/`) sind für diesen Zyklus
nicht maßgeblich, auch wenn die von ihnen beschriebene, reise-basierte
Architektur die technische Grundlage bildet.

Das Zielsystem erweitert die bestehende, reise-basierte Anwendung um einen
zweiten, unabhängigen Angebots-Anbieter (Imoova) neben Movacar. Jede Reise
erhält eine explizite Anbieterzuordnung. Für jede Reise wird pro
zugeordnetem Anbieter eine eigene, fehlerisolierte Abfrage durchgeführt.
Sofortbenachrichtigungen und geplante Übersichten werden je Anbieter in
getrennten E-Mails versendet.

Nicht Gegenstand dieses Dokuments sind Implementierungsaufgaben, Code oder
der technische Fix des in Spezifikation §5.4/§9 beschriebenen bestehenden
Movacar-Link-Fehlers (siehe Abschnitt 2 und 12).

## 2. Verbindliche Entscheidungen

| Thema | Entscheidung |
|---|---|
| Anbieter-Domänenmodell | Ein `Provider`-Enum mit den Werten `movacar` und `imoova` kennzeichnet die tatsächliche Quelle eines einzelnen Angebots. Ein separates `TripProviderSelection`-Enum mit den Werten `movacar`, `imoova`, `both` kennzeichnet die Anbieterzuordnung einer Reise und lässt sich in eine oder zwei konkrete `Provider`-Werte auflösen. |
| Anbieterfeld an der Reise | `Trip` erhält ein verpflichtendes Feld `provider: TripProviderSelection`. Bestehende Reisen ohne explizite Angabe sowie neu angelegte Reisen ohne `--provider`-Angabe erhalten den Default `movacar`, damit sich ihr Verhalten durch diesen Zyklus nicht unangekündigt ändert. |
| Angebots-ID-Namensraum | Bestehende Movacar-Angebots-IDs bleiben unverändert (kein Rename, keine Datenmigration bestehender Zeilen). Neue, von Imoova stammende Angebote erhalten beim Parsen verpflichtend das Präfix `imoova:` vor ihrer anbieterinternen ID, damit `offers.id` global eindeutig bleibt und niemals mit einer Movacar-ID kollidieren kann. |
| Angebotsspeicherung | `offers` erhält zusätzlich eine verpflichtende Spalte `provider`. Jedes Angebot gehört exakt einem `Provider` an; `both` ist an dieser Stelle kein gültiger Wert. |
| Areal-Zuordnung | Für jede bei Imoova existierende Area (z. B. Europe, Canada, ...) werden ihr Name und ein geografisches Polygon (Liste von Lat/Long-Koordinatenpaaren) in einer versionierten JSON-Konfigurationsdatei im Repository (`config/imoova_areas.json`) gepflegt und beim Programmstart einmalig geladen. Die Zuordnung einer Reise erfolgt nicht über den Städtenamen, sondern über einen Punkt-in-Polygon-Test der bereits vorhandenen `Trip.latitude`/`Trip.longitude`-Koordinaten gegen alle hinterlegten Area-Polygone. Es gibt dafür keine Datenbanktabelle und keine CLI-Verwaltung. Das in Spezifikation §7/Artefakt 3 geforderte OpenStreetMap-Skript erzeugt beziehungsweise aktualisiert genau diese Datei mit Area-Namen und den zugehörigen Polygonen. |
| Fehlende Areal-Zuordnung | Liegen die Koordinaten einer Reise in keinem der hinterlegten Area-Polygone (Punkt-in-Polygon-Test liefert `None`), wird diese Reise für den Anbieter Imoova in diesem Zyklus übersprungen (kein Fehler, sichtbares Protokoll); andere zugeordnete Anbieter dieser Reise sind davon unberührt. |
| Imoova-Endpunkt und Datumsparameter | Bestätigt: `build_imoova_trip_url(imoova_api_url, area, trip)` folgt dem Muster `{imoova_api_url}/relocations/{area}?earliest_departure={date}`. `area` ist der von `resolve_area` gelieferte Area-Name, `date` entspricht `trip.pickup_start` in identischer Syntax wie beim bestehenden `build_trip_url` für Movacar (keine Umformatierung notwendig). |
| Authentifizierung, Rate-Limits, Retry (Imoova) | Es wird zum Planungszeitpunkt keine Authentifizierung angenommen (keine Header, Tokens oder API-Keys). Rate-Limits, Timeout- und Retry-Verhalten werden unverändert vom bestehenden Movacar-Client übernommen (`HTTP_TIMEOUT_SECONDS`, Retry-Delays `(1, 2, 4)` Sekunden). |
| Polling | Pro Reise wird für jeden aus `trip.provider` aufgelösten `Provider`-Wert eine eigene Anfrage gestellt. Jede dieser Anfragen ist einzeln fehlerisoliert: Ein fehlgeschlagener Anbieter beeinflusst weder den anderen Anbieter derselben Reise noch andere Reisen. |
| Verfügbarkeitsabgleich | Der Verfügbarkeitsabgleich einer Reise wird anbieterbezogen durchgeführt: Eine vollständige Antwort eines Anbieters darf ausschließlich Zuordnungen desselben Anbieters für dieselbe Reise als nicht verfügbar markieren, niemals Zuordnungen des anderen Anbieters. |
| E-Mail-Versand | Sofortbenachrichtigungen und die Übersichten um 09:00/21:00 Uhr (`Europe/Berlin`) werden strikt je Reise **und** je Anbieter in getrennten E-Mails versendet. Eine Reise mit `both` kann pro Zyklus bis zu zwei unabhängige Sofortmails und zu zwei unabhängige Übersichtsmails erzeugen. |
| Anbieterkennzeichnung in Mails | Jede E-Mail zeigt Reisename und den erzeugenden Anbieter (z. B. „Movacar“ / „Imoova“) sichtbar in Betreff und Kopfbereich, wie in Spezifikation §5.3 gefordert. |
| Distanzberechnung | Unverändert Haversine, Kilometer, eine Nachkommastelle für die Darstellung, dieselben Schwellen wie in `plan_v2.1.md` (siehe Abschnitt 7.3). Gilt anbieterunabhängig, sofern die jeweilige Anbieterantwort Ursprungskoordinaten liefert. |
| Movacar-Client | `src/api/api_client.py` und `build_trip_url` bleiben in ihrer heutigen Form unverändert bestehen; sie sind nicht Gegenstand dieses Plans. |
| Link-Fehler (Movacar) | Der in Spezifikation §5.4/§9 beschriebene, historisch gemeldete Fehler (Link zeigt auf ein Quellverzeichnis) wird vom Nutzer selbst außerhalb dieses Umsetzungszyklus behoben und ist daher kein Ausführungsgegenstand dieses Plans (siehe Abschnitt 12). Die für Imoova neu eingeführte Link-Erzeugung folgt von Beginn an demselben Grundsatz wie der bestehende Movacar-Code-Pfad: Der angezeigte Link muss exakt der tatsächlich verwendeten GET-Anfrage-URL entsprechen. |
| CLI | Das Verwaltungswerkzeug erhält eine optionale `--provider`-Option bei `trip create` (Default `movacar`) sowie einen neuen Unterbefehl `trip provider set`, um die Anbieterzuordnung einer bestehenden Reise zu ändern. |
| Testausführung | Unit-Tests für jede neue oder geänderte Funktion sowie ein erweiterter, hermetischer E2E-Test mit Test-Doubles für Movacar **und** Imoova. |

## 3. Bestandsarchitektur und Änderungsmatrix

| Bestehende Komponente | Aktuelles Verhalten | Zielverhalten und Maßnahme |
|---|---|---|
| `src/models/trip.py` / `src/models/offer.py` (`Trip`) | `Trip` besitzt kein Anbieterfeld; kennt nur reisebezogene Stammdaten. | Erhält verpflichtendes Feld `provider: TripProviderSelection` mit Default `movacar` sowie eine abgeleitete Methode zur Auflösung in ein oder zwei `Provider`-Werte. |
| `src/models/offer.py` (`Offer`) | `Offer` kennt keine Anbieterherkunft; IDs sind implizit Movacar-IDs. | Erhält verpflichtendes Feld `provider: Provider`. Validierung stellt sicher, dass IDs des Anbieters Imoova mit `imoova:` beginnen. |
| `src/models/offer.py` (`TripOfferView`, `DistanceTier`) | Unverändert reisespezifisch, anbieterunabhängig. | Bleibt inhaltlich unverändert; die Anbieterinformation ist über `offer.provider` bereits enthalten, kein zusätzliches Feld nötig. |
| `src/storage/sqlite_store.py` | `SCHEMA_VERSION = 4`; `offers` und `trips` ohne Anbieterspalte; Verfügbarkeitsabgleich (`_mark_missing_trip_offers_unavailable`) sowie die Leseabfragen (`list_new_unsent_available_trip_offers`, `list_available_trip_offers`, `synchronize_trip_offers`, `reconcile_trip_offer_availability`) arbeiten ausschließlich über `trip_id`, ohne Anbieterbezug. | Neue additive Migration `SCHEMA_VERSION = 5`: fügt `offers.provider` und `trips.provider` hinzu (`NOT NULL DEFAULT 'movacar'`, additiv per `ALTER TABLE ADD COLUMN`, analog zu den bestehenden Migrationen für Koordinaten und Preis). Alle genannten Methoden erhalten zusätzlich einen `provider`-Parameter und filtern beziehungsweise reconcilen ausschließlich innerhalb dieses Anbieters für die jeweilige Reise. |
| `src/api/api_client.py` | Movacar-spezifischer HTTP-Client mit Retry-Delays `(1, 2, 4)` Sekunden und `build_trip_url`. | Bleibt unverändert (siehe Abschnitt 2, „Movacar-Client“). Keine Änderung, keine Wiederverwendung durch Imoova außer der gemeinsamen Retry-Konstante als Vorbild. |
| *(neu)* `src/api/imoova_client.py` | Existiert nicht. | Neues Modul mit `fetch_imoova_offers(settings, trip, area)` und `build_imoova_trip_url(imoova_api_url, area, trip)`, strukturell analog zu `api_client.py` (gleiche Retry-Delays, gleiche Fehlerklassen-Hierarchie, eigener Namensraum `ImoovaApiError` und Subklassen). |
| `src/parser/offer_parser.py` | `parse_offers` erzeugt `Offer`-Objekte aus dem Movacar-JSON:API-Format (`data`/`included`, `station`, `monetary_amount`). | Erhält minimal die Ergänzung, jedem erzeugten `Offer` `provider=Provider.MOVACAR` zu setzen; die bestehende All-or-nothing-Validierung und Feldstruktur bleiben unverändert. |
| *(neu)* `src/parser/imoova_offer_parser.py` | Existiert nicht. | Neues Modul mit `parse_imoova_offers(response)`, das Imoovas Antwortformat (Struktur zu verifizieren, siehe Abschnitt 11.3) in dieselben `Offer`-Objekte überführt, IDs mit `imoova:` präfixiert und `provider=Provider.IMOOVA` setzt. Dieselbe All-or-nothing-Garantie wie beim Movacar-Parser gilt hier ebenfalls. |
| *(neu)* `src/areas/imoova_area_resolver.py` | Existiert nicht. | Neues Modul, das `config/imoova_areas.json` einmalig lädt (Area-Name plus zugehöriges Polygon je Area) und `resolve_area(latitude: float, longitude: float) -> str \| None` bereitstellt. Die Auflösung erfolgt über einen Punkt-in-Polygon-Test der übergebenen Koordinaten gegen alle hinterlegten Area-Polygone und liefert `None`, wenn kein Polygon die Koordinaten enthält. |
| *(neu)* Skript zur Areal-Berechnung | Existiert nicht. | Eigenständiges, wiederholbar ausführbares Skript (z. B. `scripts/build_imoova_area_mapping.py`), das auf Basis von OpenStreetMap für jede Imoova-Area Name und geografisches Polygon ermittelt und in `config/imoova_areas.json` erzeugt beziehungsweise aktualisiert. Läuft nicht im Polling-Pfad. |
| `src/synchronization/trip_offer_synchronizer.py` | `synchronize_trip_offers(store, trip, offers)` berechnet Distanzen und ruft `store.synchronize_trip_offers(trip.trip_id, offers_with_distances)` für die gesamte Reise auf, ohne Anbieterbezug. | Erhält zusätzlich einen `provider: Provider`-Parameter und reicht ihn an die anbieterbezogenen Store-Methoden durch. Wird pro Anbieter einer Reise separat aufgerufen. |
| `src/loop/poll_loop.py` (`_process_one_trip`) | Führt pro Reise genau einen Fetch-/Parse-/Synchronisierungs-/Versand-Durchlauf mit dem einzigen konfigurierten Movacar-Anbieter aus. | Wird zu einer Schleife über die aus `trip.provider` aufgelösten `Provider`-Werte erweitert: Für jeden Anbieter läuft derselbe Ablauf (Fetch → Parse → Synchronisieren → Sofortmail → Übersicht) mit provider-spezifischem Client, Parser und `offers_url`, vollständig fehlerisoliert je Anbieter. Liegen die Reisekoordinaten in keinem hinterlegten Area-Polygon, wird dieser Anbieter für die Reise übersprungen und protokolliert, ohne den Movacar-Durchlauf zu beeinträchtigen. |
| `src/notifications/trip_mail_view.py` (`TripMailView`, `prepare_trip_mail_view`) | Liest reisebezogene, anbieterunabhängige Empfänger- und Angebotslisten. | `prepare_trip_mail_view` erhält einen `provider: Provider`-Parameter und liest ausschließlich Angebote dieses Anbieters. `TripMailView` erhält ein zusätzliches Feld `provider: Provider`, das gegen alle enthaltenen `TripOfferView`-Einträge validiert wird. |
| `src/notifications/instant_notification.py`, `src/notifications/trip_summary.py` | Erzeugen genau eine Sofortmail bzw. Übersichtsmail pro Reise mit anbieterneutralem Betreff. | Erhalten einen `provider: Provider`-Parameter, reichen ihn an `prepare_trip_mail_view` durch und ergänzen den E-Mail-Betreff um die Anbieterbezeichnung (z. B. „Neue Angebote für {Reise} (Imoova)“). |
| `src/mailer/templates.py` | Rendert Titel „Neue Movacar-Angebote“ / „Aktuelle Movacar-Angebote“ fest verdrahtet auf Movacar. | Rendert die Anbieterbezeichnung dynamisch aus `view.provider` statt eines festen „Movacar“-Textes; HTML-Struktur und Distanzstufen-Darstellung bleiben unverändert. |
| `src/loop/summary_schedule.py` | `has_trip_overview_slot`/`mark_trip_overview_slot_sent` (über `sqlite_store.py`) sind ausschließlich `(trip_id, local_date, slot_hour)`-adressiert. | `trip_overview_slots` und die zugehörigen Store-Methoden erhalten zusätzlich `provider`, damit für dieselbe Reise beide Anbieter unabhängig ihren 09:00/21:00-Slot verwalten. Die Zeitplanlogik selbst (`latest_due_summary_slot`) bleibt unverändert. |
| `src/config/settings.py` | `Settings` kennt nur `api_url` (Movacar) sowie allgemeine SMTP-/SQLite-/Timeout-Einstellungen. | Erhält zusätzliche, optionale Felder für Imoova (`imoova_api_url: str \| None`, `imoova_areas_path: Path`). Ist `imoova_api_url` nicht gesetzt, wird Imoova für alle Reisen faktisch deaktiviert und dies sichtbar protokolliert, selbst wenn einzelne Reisen `imoova`/`both` zugeordnet sind. |
| `src/admin_cli.py` | `trip create` kennt keine Anbieterzuordnung; es gibt keinen Befehl zum Ändern der Anbieterzuordnung. | `trip create` erhält eine optionale `--provider`-Option (Default `movacar`). Neuer Unterbefehl `trip provider set --trip-id --provider` ändert die Anbieterzuordnung einer bestehenden Reise. `trip list` gibt den Anbieter mit aus. |
| `README.md` | Dokumentiert die reine Movacar-Integration. | Ergänzt um Anbieterkonzept, Imoova-Konfiguration, Areal-Konfigurationsdatei und die neuen CLI-Optionen. |
| Bestehende Tests | Prüfen ausschließlich den einzigen, Movacar-spezifischen Pfad ohne Anbieterparameter. | Werden um den `provider`-Parameter ergänzt; zusätzliche Tests für Imoova-Client, Imoova-Parser, Areal-Resolver, provider-bezogene Synchronisierung/Reconciliation und CLI-Erweiterungen kommen hinzu. |

## 4. Zielarchitektur

### 4.1 Komponenten und Verantwortlichkeiten

| Zielkomponente | Verantwortung |
|---|---|
| Reiseverwaltung | Validiert und persistiert Reisen inklusive Anbieterzuordnung (`TripProviderSelection`). |
| Verwaltungs-CLI | Unterbefehle für Reisen, Empfänger und Anbieterzuordnung (`trip provider set`). |
| Movacar-Client | Unverändert: HTTP-Request für den Reisezeitraum bauen, wiederholen, Antwort transportieren. |
| Imoova-Client | Löst die Imoova-Area über den Areal-Resolver anhand der Reisekoordinaten auf, baut den Imoova-spezifischen Request (ohne Authentifizierung), wiederholt ihn nach demselben Muster wie der Movacar-Client und transportiert die Antwort. |
| Movacar-Parser | Unverändert: normalisiert Movacar-Antworten zu `Offer`-Objekten mit `provider=movacar`. |
| Imoova-Parser | Normalisiert Imoova-Antworten zu `Offer`-Objekten mit `provider=imoova` und präfixierten IDs. |
| Areal-Resolver | Lädt `config/imoova_areas.json` (Area-Name plus Polygon je Area) und löst die Koordinaten einer Reise (`latitude`/`longitude`) per Punkt-in-Polygon-Test in eine Imoova-Area auf oder liefert `None`. |
| Reise-Synchronisierer | Berechnet Distanzen und persistiert ein vollständiges Anbieter-Ergebnis einer Reise atomar und anbieterbezogen. |
| Angebots-/Zuordnungs-Repository | Speichert Angebote inklusive Anbieter, führt Reise-Angebot-Zuordnungen und führt Verfügbarkeitsabgleich strikt anbieterbezogen durch. |
| Benachrichtigungsservice | Liest neue/verfügbare Angebote einer Reise **für genau einen Anbieter**, erstellt die Mail-Ansicht, sendet und persistiert Versand- bzw. Slot-Status für diesen Anbieter. |
| E-Mail-Composer | Rendert HTML mit dynamischer Anbieterbezeichnung in Titel, Kopfbereich und Betreff. |
| SMTP-Mailer | Unverändert: sendet an explizit übergebene Empfänger, kennt weder Reise noch Anbieter inhaltlich. |
| Zeitplanlogik | Unverändert: bestimmt die lokalen Slots 09:00/21:00 Uhr; Persistenz des „bereits gesendet“-Zustands wird anbieterbezogen erweitert. |
| Orchestrator (`poll_loop`) | Lädt alle Reisen, löst je Reise die zugeordneten Anbieter auf und verarbeitet jede Reise-Anbieter-Kombination sequenziell und einzeln fehlerisoliert. |

### 4.2 Abhängigkeitsrichtung

Der Orchestrator hängt von den provider-spezifischen Clients, Parsern, dem
Areal-Resolver und den anbieterbezogenen Repository-Schnittstellen ab. Der
Movacar- und der Imoova-Client sind voneinander unabhängig und teilen sich
keinen Code außer dem allgemeinen Retry-Musters. Templates erhalten weiterhin
ausschließlich fertige `TripMailView`-Objekte inklusive Anbieterfeld und
greifen nicht auf SQLite, Settings oder externe Dienste zu. Der SMTP-Mailer
bleibt unverändert unabhängig von Reise- und Anbieterdaten.

## 5. Datenmodell, Zustände und Migration

### 5.1 Migration (Schema-Version 5)

| Änderung | Ausführung |
|---|---|
| `offers.provider` | `ALTER TABLE offers ADD COLUMN provider TEXT NOT NULL DEFAULT 'movacar'`, additiv, idempotent geprüft wie bestehende Spalten-Migrationen. Bestehende Zeilen werden automatisch auf `'movacar'` befüllt. |
| `trips.provider` | `ALTER TABLE trips ADD COLUMN provider TEXT NOT NULL DEFAULT 'movacar'`, gleiches Verfahren. Bestehende Reisen bleiben damit unverändert ausschließlich Movacar zugeordnet. |
| `trip_overview_slots.provider` | `ALTER TABLE trip_overview_slots ADD COLUMN provider TEXT NOT NULL DEFAULT 'movacar'` sowie Erweiterung des Primärschlüssel-Verhaltens auf `(trip_id, local_date, slot_hour, provider)` über einen neuen eindeutigen Index, da SQLite Primärschlüssel nicht nachträglich ändert. |
| Migrationsvertrag | Wie in `plan_v2.1.md` §5.4 festgelegt: versioniert, additiv, transaktional, idempotent; der Dienst startet das Polling erst nach erfolgreicher Migration. |

`trip_offers` und `trip_recipients` bleiben strukturell unverändert; die
Anbieterinformation eines Angebots ist über `trip_offers.offer_id →
offers.provider` bereits eindeutig ableitbar.

### 5.2 Zustandsregeln (Ergänzungen zu `plan_v2.1.md` §5.2)

- Ein globales Angebot gehört exakt einem `Provider` an; dieser wird beim
  Anlegen gesetzt und ändert sich nie.
- Der Verfügbarkeitsabgleich für eine Reise und einen Anbieter darf
  ausschließlich Zuordnungen betreffen, deren Angebot demselben Anbieter
  angehört. Eine vollständige Movacar-Antwort verändert niemals den
  Verfügbarkeitszustand von Imoova-Zuordnungen derselben Reise und
  umgekehrt.
- Versandstatus (`is_sent`) und Übersichtsslot-Status werden pro Reise **und**
  Anbieter unabhängig geführt; eine Reise mit `both` kann für Movacar und
  Imoova unterschiedliche, unabhängige Sendehistorien haben.
- Liegen die Koordinaten einer Reise in keinem hinterlegten Area-Polygon,
  entsteht für den Anbieter Imoova in diesem Zyklus keine Zuordnung, keine
  Verfügbarkeitsänderung und keine Sendehandlung; der Movacar-Anteil
  derselben Reise ist unberührt.

### 5.3 Historische Daten

Bestehende `offers`-Zeilen erhalten beim Anwenden der Migration automatisch
`provider = 'movacar'` und bleiben unter ihrer bisherigen ID ansprechbar; es
findet keine ID-Umbenennung statt. Bestehende `trips`-Zeilen erhalten
`provider = 'movacar'` und werden dadurch inhaltlich nicht verändert.

## 6. End-to-End-Datenflüsse

### 6.1 Verwaltung per CLI

1. `trip create` validiert zusätzlich die optionale `--provider`-Angabe
   (Default `movacar`) gegen `TripProviderSelection`.
2. `trip provider set` validiert Reiseexistenz und neuen Anbieterwert und
   aktualisiert `trips.provider` transaktional.
3. Ungültige Anbieterwerte enden mit nachvollziehbarer Meldung und
   nicht-null Exit-Code, analog zu den bestehenden CLI-Fehlerpfaden.

### 6.2 Reisebasierter, anbieterbezogener Polling-Zyklus

1. Der Orchestrator lädt alle Reisen und verarbeitet sie sequenziell wie
   bisher.
2. Für jede Reise löst er `trip.provider` in eine oder zwei konkrete
   `Provider`-Werte auf.
3. Für jeden aufgelösten Anbieter läuft ein eigener, vollständig
   fehlerisolierter Unterablauf:
   - Movacar: unveränderter bestehender Ablauf (`fetch_offers`,
     `parse_offers`, Distanzberechnung, Synchronisierung).
   - Imoova: Areal-Resolver löst die Reisekoordinaten (`latitude`/
     `longitude`) per Punkt-in-Polygon-Test in eine Area auf; enthält kein
     hinterlegtes Polygon diese Koordinaten, wird dieser Unterablauf
     protokolliert übersprungen; sonst `fetch_imoova_offers`,
     `parse_imoova_offers`, dieselbe Distanzberechnung, anbieterbezogene
     Synchronisierung.
4. Nach erfolgreicher anbieterbezogener Synchronisierung wird für diesen
   Anbieter eine eigene Sofortmail (falls neue Angebote vorliegen) und eine
   eigene, slot-gesteuerte Übersichtsmail geprüft und ggf. versendet.
5. Ein Fehler in einem Anbieter-Unterablauf wird mit Reise-ID/-Name und
   Anbieter protokolliert; der Orchestrator fährt mit dem nächsten Anbieter
   beziehungsweise der nächsten Reise fort.

### 6.3 Sofortbenachrichtigung und Übersicht (Ergänzung zu `plan_v2.1.md` §6.4/§6.5)

Beide Abläufe entsprechen inhaltlich `plan_v2.1.md`, jedoch strikt für genau
einen `Provider` pro Aufruf: Angebotslisten, Mail-Ansicht, Betreff,
Empfänger-Selektion und Versandstatus-Persistenz sind ausschließlich auf
diesen Anbieter bezogen. Eine Reise mit `both` durchläuft diesen Ablauf bis
zu zweimal pro Zyklus, unabhängig voneinander.

## 7. Schnittstellen und Vertragsänderungen

### 7.1 Imoova-Client

`fetch_imoova_offers(settings, trip, area)` erhält die bereits aufgelöste
Imoova-Area sowie den Reisezeitraum und liefert entweder eine valide
Rohantwort oder einen spezifischen Transport-/Antwortfehler, strukturell
analog zu `fetch_offers`. Der Endpunkt ist bestätigt: `build_imoova_trip_url`
erzeugt eine URL nach dem Muster
`{imoova_api_url}/relocations/{area}?earliest_departure={date}`, wobei
`area` der von `resolve_area` gelieferte Area-Name ist und `date` dem Wert
von `trip.pickup_start` entspricht — identische Syntax wie bei
`build_trip_url` für Movacar, keine Umformatierung notwendig. Es wird keine
Authentifizierung angenommen (keine Header, Tokens oder API-Keys).
Rate-Limits, Timeout- und Retry-Verhalten entsprechen unverändert dem
bestehenden Movacar-Client (`HTTP_TIMEOUT_SECONDS`, Retry-Delays
`(1, 2, 4)` Sekunden). Offen bleibt zum Planungszeitpunkt weiterhin das
vollständige Antwortformat (siehe Abschnitt 11.3).

### 7.2 Imoova-Parser und Angebotsmodell

`parse_imoova_offers` behält denselben All-or-nothing-Validierungsvertrag wie
`parse_offers`: Ein unvollständig auflösbares Angebot invalidiert die gesamte
Antwort. Jedes erzeugte `Offer` erhält `provider = imoova` und eine mit
`imoova:` präfixierte ID. Welche Imoova-Antwortfelder auf `free_km`, Preis und
Ursprungs-/Zielkoordinaten abgebildet werden, ist erst nach Verifikation der
tatsächlichen API-Struktur endgültig festzulegen.

### 7.3 Distanzdienst

Unverändert gegenüber `plan_v2.1.md` §7.3: Haversine-Kilometer, Rundung nur
zur Darstellung, Klassifikation `<100`, `>=100 und <250`, `>=250 und <500`,
`>=500`. Voraussetzung ist, dass die Imoova-Antwort Ursprungskoordinaten in
derselben Genauigkeit wie Movacar liefert; ist dies nicht der Fall, ist dies
ein Punkt für die TASK-Phase (siehe Abschnitt 11.3).

### 7.4 Persistenz

Alle in Abschnitt 3 genannten Repository-Methoden erhalten einen
verpflichtenden `provider`-Parameter und dürfen niemals anbieterübergreifend
lesen, schreiben oder reconcilen. Eine Abfrage ohne Anbieterbezug für eine
Reise mit mehreren Anbietern ist ein Vertragsbruch.

### 7.5 E-Mail-Composer, Notification-Services und SMTP

`prepare_trip_mail_view`, `send_instant_trip_notification` und
`send_due_trip_summary` erhalten je einen verpflichtenden
`provider`-Parameter. `TripMailView` führt zusätzlich `provider` als Feld und
validiert es gegen jedes enthaltene Angebot. Templates rendern die
Anbieterbezeichnung dynamisch. Der SMTP-Mailer (`send_html_email`) bleibt
unverändert; er erhält weiterhin nur Empfänger, HTML-Inhalt und Betreff ohne
Kenntnis von Reise oder Anbieter.

### 7.6 Konfiguration

| Konfiguration | Zielvertrag |
|---|---|
| `API_URL` und alle bestehenden Movacar-/SMTP-/SQLite-/Timeout-/Logging-Einstellungen | Bleiben unverändert erforderlich. |
| `IMOOVA_API_URL` (neuer, optionaler Wert) | Basis-URL für den Imoova-Client. Fehlt dieser Wert, wird Imoova für alle Reisen deaktiviert und dies sichtbar protokolliert, auch wenn einzelne Reisen `imoova`/`both` zugeordnet sind. |
| `IMOOVA_AREAS_PATH` (neuer, optionaler Wert mit Default `config/imoova_areas.json`) | Pfad zur Areal-Zuordnungsdatei. |
| Anbieterzuordnung je Reise | Liegt ausschließlich in `trips.provider`, nicht in Umgebungsvariablen. |
| Areal-Zuordnungstabelle | Liegt ausschließlich in `config/imoova_areas.json`, nicht in der Datenbank und nicht in Umgebungsvariablen. |

Authentifizierung, Rate-Limits und Timeout-/Retry-Parameter für Imoova sind
bestätigt: keine Authentifizierung, sowie identische Timeout- und
Retry-Delays wie beim bestehenden Movacar-Client (`HTTP_TIMEOUT_SECONDS`,
`(1, 2, 4)` Sekunden).

## 8. Refactorings und Rückwärtskompatibilität

### 8.1 Gezielte Refactorings

- `_mark_missing_trip_offers_unavailable`, `synchronize_trip_offers`,
  `reconcile_trip_offer_availability`, `list_new_unsent_available_trip_offers`
  und `list_available_trip_offers` in `sqlite_store.py` werden um einen
  `provider`-Parameter erweitert und filtern beziehungsweise reconcilen
  ausschließlich innerhalb dieses Anbieters.
- `_process_one_trip` in `poll_loop.py` wird von einem einzelnen
  Verarbeitungspfad pro Reise zu einer inneren Schleife über die aufgelösten
  Anbieter dieser Reise umgebaut, wobei jede Iteration eigenständig
  fehlerisoliert bleibt.
- `prepare_trip_mail_view`, `send_instant_trip_notification` und
  `send_due_trip_summary` werden um den `provider`-Parameter erweitert; ihr
  bestehendes Fehlerverhalten (`MissingTripRecipientsError`, Rückgabe eines
  Boolean-Erfolgswerts) bleibt unverändert erhalten.
- `templates.py` verliert die feste Movacar-Beschriftung und rendert die
  Anbieterbezeichnung aus `view.provider`.

### 8.2 Garantien beim Übergang

- Bestehende Reisen ohne explizite Anbieterangabe bleiben nach der Migration
  ausschließlich Movacar-Reisen; ihr beobachtbares Verhalten (Anzahl und
  Inhalt der E-Mails) ändert sich durch diesen Zyklus nicht.
- Bestehende Movacar-Angebots-IDs und ihr Verfügbarkeits-/Versandzustand
  bleiben unverändert erhalten; es findet keine rückwirkende Neubewertung
  statt.
- Es gibt weiterhin keinen anbieterübergreifenden Fallback-Pfad: Ein
  fehlender oder fehlerhafter Imoova-Anbieter blockiert niemals den
  Movacar-Anteil einer Reise und umgekehrt.
- Der Dienst bleibt mit einer vorhandenen Alt-`.env` ohne
  `IMOOVA_API_URL`/`IMOOVA_AREAS_PATH` startbar; Imoova ist in diesem Fall
  für alle Reisen inaktiv, unabhängig von deren `provider`-Wert.

## 9. Seiteneffekte und Betrieb

| Bereich | Auswirkung und Behandlung |
|---|---|
| API-Last | Reisen mit `provider = both` erzeugen pro Zyklus zwei Requests statt einem. Sequenzielle, anbieterweise Verarbeitung begrenzt Parallelität weiterhin, verlängert aber die Zyklusdauer zusätzlich. |
| SMTP-Volumen | Reisen mit `both` können pro Zyklus bis zu zwei Sofortmails und zu zwei Übersichtsmails erzeugen, statt bisher höchstens einer je Mailtyp. Empfänger mehrerer solcher Reisen erhalten entsprechend mehr, fachlich getrennte Nachrichten. |
| Zustandskonsistenz | Synchronisierung und Verfügbarkeitsabgleich bleiben je Reise **und** Anbieter atomar; ein Anbieter-Fehler verändert nie den Zustand des anderen Anbieters derselben Reise. |
| Areal-Abdeckung | Reisen, deren Koordinaten in keinem Polygon aus `config/imoova_areas.json` liegen, bleiben für Imoova dauerhaft inaktiv, bis die Konfigurationsdatei aktualisiert wird; dies wird bei jedem Zyklus sichtbar protokolliert, nicht nur einmalig. |
| Logging | Jede operative Meldung enthält zusätzlich zu Reise-ID/-Name den betroffenen Anbieter, damit Fehler eindeutig einem Anbieter-Unterablauf zugeordnet werden können. |
| Konfigurationsbetrieb | Ein fehlender `IMOOVA_API_URL`-Wert ist ein bewusst unterstützter Betriebszustand (Imoova inaktiv) und kein Startfehler. |

## 10. Teststrategie

### 10.1 Zu ergänzende und anzupassende Tests

Bestehende Tests für `sqlite_store.py`, `poll_loop.py`, `trip_mail_view.py`,
`instant_notification.py`, `trip_summary.py` und `templates.py` werden um den
`provider`-Parameter beziehungsweise die anbieterabhängige Erwartung
ergänzt. Sie prüfen zusätzlich, dass ein Movacar-Vorgang niemals
Imoova-Zustand verändert und umgekehrt.

### 10.2 Neue Unit-Tests

- Migration auf `SCHEMA_VERSION = 5`: Idempotenz, Backfill auf `movacar`,
  additive Spalten für `offers`, `trips` und `trip_overview_slots`.
- `TripProviderSelection`-Auflösung in ein oder zwei `Provider`-Werte.
- Imoova-Client: Request-Bildung aus Area und Reisezeitraum, Retry-Verhalten,
  Fehlerklassifikation, analog zu bestehenden Movacar-Client-Tests.
- Imoova-Parser: vollständige Angebote, All-or-nothing bei unvollständigen
  Daten, korrekte `imoova:`-Präfixierung und `provider`-Zuweisung.
- Areal-Resolver: bekannte und unbekannte Startstädte, fehlende
  Konfigurationsdatei.
- Anbieterbezogene Synchronisierung und Reconciliation: Eine vollständige
  Antwort eines Anbieters verändert nachweislich nicht die Zuordnungen des
  anderen Anbieters derselben Reise.
- Getrennte Sofort- und Übersichtsmails je Anbieter, inklusive korrekter
  Anbieterbezeichnung in Betreff und Kopfbereich.
- CLI: `trip create --provider`, `trip provider set`, Validierungsfehler bei
  ungültigen Anbieterwerten und deren Exit-Codes.

### 10.3 Erweiterter hermetischer E2E-Test

Ergänzt den bestehenden E2E-Test aus `plan_v2.1.md` §10.3 um mindestens:

1. Eine Reise mit `provider = both`, unterschiedlichen Test-Doubles für
   Movacar und Imoova und unabhängiger Erstbenachrichtigung je Anbieter.
2. Einen Fehler im Imoova-Unterablauf einer Reise, während der
   Movacar-Unterablauf derselben Reise erfolgreich verarbeitet und
   versendet wird, und umgekehrt.
3. Eine Reise mit `provider = imoova`, deren Koordinaten in keinem
   hinterlegten Area-Polygon liegen: kein Imoova-Request, keine
   Imoova-Mail, sichtbares Protokoll.
4. Unabhängige 09:00/21:00-Übersichtsslots je Anbieter für dieselbe Reise.

Kein automatisierter Test kontaktiert Gmail, Movacar, Imoova, OpenStreetMap
oder einen anderen externen Dienst.

## 11. Annahmen, Risiken und offene Punkte

### 11.1 Annahmen

| Annahme | Auswirkung bei Abweichung |
|---|---|
| Imoova liefert für jedes Angebot Ursprungskoordinaten in vergleichbarer Genauigkeit wie Movacar. | Distanzberechnung und Highlighting für Imoova-Angebote müssten eingeschränkt oder mit einer Ersatzlogik versehen werden. |
| `config/imoova_areas.json` lässt sich mit vertretbarem Aufwand aktuell halten, sobald eine gültige Areas-Liste vorliegt. | Ohne aktuelle Datei bleibt Imoova für betroffene Reisen dauerhaft inaktiv. |
| SQLite `ALTER TABLE ADD COLUMN` reicht für alle in Abschnitt 5.1 genannten additiven Änderungen aus. | Für `trip_overview_slots` müsste statt eines neuen eindeutigen Index eine Tabellen-Neuerstellung samt Datenübernahme vorgesehen werden. |

### 11.2 Risiken

| Risiko | Minderung |
|---|---|
| Das tatsächliche Imoova-Antwortformat (Feldnamen, Verschachtelung, Einheiten) weicht von der angenommenen Struktur ab, obwohl Endpunkt und Query-Parameter bereits bestätigt sind. | Verifikation per direktem Testaufruf vor Beginn der TASK-Phase (siehe 11.3); der Imoova-Parser wird erst nach Bestätigung final spezifiziert. |
| Ein Area-Polygon deckt eine Reisekoordinate fälschlich nicht ab (z. B. zu grob vereinfachtes Polygon nahe einer Grenze) oder zwei Polygone überlappen sich. | Sichtbares, wiederkehrendes Protokoll pro Zyklus statt einmaligem Hinweis; Polygon-Datei ist versioniert und leicht nachpflegbar; Behandlung von Grenzfällen wird vor der TASK-Phase geklärt (siehe 11.3). |
| Getrennter Versand je Anbieter erhöht SMTP-Volumen zusätzlich zur bereits bestehenden Erhöhung durch mehrere Reisen. | Beobachtung des Versandvolumens im Betrieb; keine technische Begrenzung in diesem Zyklus vorgesehen. |
| Eine anbieterübergreifende Vermischung im Verfügbarkeitsabgleich (z. B. durch eine vergessene `provider`-Filterung) würde fälschlich Angebote des anderen Anbieters als nicht verfügbar markieren. | Verpflichtender `provider`-Parameter an allen betroffenen Repository-Methoden; dedizierte Tests gemäß Abschnitt 10.2, die diese Vermischung explizit ausschließen. |

### 11.3 Vor TASK-Phase zu bestätigen

Endpunkt, Query-Parameter (`earliest_departure` = `trip.pickup_start`,
identische Syntax wie bei Movacar), Authentifizierung (keine) sowie
Rate-Limits/Timeout/Retry (identisch zu Movacar) sind bereits durch diese
Rückmeldung geklärt und nicht mehr Teil dieser Liste. Offen bleiben:

- Das vollständige Imoova-Antwortformat für Route, Zeitraum, Preis und
  Verfügbarkeit (genaue Feldnamen, Verschachtelung, Einheiten); dies
  erfordert einen direkten Testaufruf gegen die echte API, um den Parser
  exakt zu spezifizieren.
- Herkunft, Pflegeprozess und initialer Befüllungsweg von
  `config/imoova_areas.json`, einschließlich des genauen Verfahrens, mit dem
  das OpenStreetMap-Skript pro Imoova-Area (z. B. Europe, Canada) das
  zugehörige Polygon ermittelt, welche Genauigkeit/Auflösung die Polygone
  haben, und des Umgangs mit Grenzfällen (Koordinate exakt auf der
  Polygongrenze, sich überlappende Polygone).
- Ob Imoova für dieselben Ursprungsstationen dieselbe Koordinatengenauigkeit
  liefert wie Movacar, oder ob die Distanzberechnung für Imoova-Angebote
  angepasst werden muss.
- Der konkrete Umfang der Test-Doubles für Imoova im E2E-Test.

Der technische Fix des bestehenden Movacar-Link-Fehlers ist ausdrücklich
**nicht** Teil dieser Liste, da der Nutzer ihn separat außerhalb dieses
Plans umsetzt (siehe Abschnitt 2 und 12).

## 12. Explizite Nichtbestandteile

- Neue Produktfunktionen außerhalb von `spec_v3.0.md`.
- Eine vollständig generische Architektur für mehr als zwei Anbieter.
- Der technische Fix des bestehenden Movacar-Link-Fehlers; dieser wird vom
  Nutzer selbst außerhalb dieses Umsetzungszyklus behoben.
- Eine Datenbanktabelle oder CLI-Verwaltung für die Imoova-Areal-Zuordnung.
- Eine nachträgliche Umbenennung oder Migration bestehender Movacar-IDs.
- Automatische Laufzeit-Geocodierung als Voraussetzung für Reisen (bleibt
  wie in `plan_v2.1.md` §12 ausgeschlossen).
- Echte externe Netzwerkaufrufe im automatisierten E2E-Test.
- Aufgabenzerlegung für die Umsetzung; diese gehört zur TASK-Phase.
- Implementierungscode; dieser gehört zur anschließenden Umsetzungsphase.
