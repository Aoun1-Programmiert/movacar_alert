# Plan v2.0: Reise-basierte Konfiguration und Benachrichtigungen

## 1. Plan-Ziel und Geltungsbereich

Dieser Plan konkretisiert die Umsetzung von `spec_v2.0.md`. Movacar Alert wird
von einer globalen Angebotsabfrage zu einem reisebasierten Ablauf erweitert:
Reisen, Empfänger und ihre Angebots- und Benachrichtigungszustände werden
dauerhaft verwaltet. Jede Reise wird separat abgefragt, räumlich bewertet und
an ihre eigenen Empfänger versendet.

Dieser Plan definiert Architektur, Modulgrenzen, Datenflüsse, Verträge,
Persistenz, Konfiguration und Teststrategie. Er erzeugt keine umsetzbaren
Aufgaben und enthält keine Implementierung.

## 2. Verbindliche Grundlagen

- SQLite bleibt die lokale Persistenz für Reisen, Empfänger und Angebote.
- Die bestehende Movacar-kompatible API bleibt die Angebotsquelle.
- Jede gespeicherte Reise löst einen eigenen API-Request mit ihrem
  Pick-up-Zeitraum aus.
- Eine Reise enthält Name, Beginn und Ende des Pick-up-Zeitraums, Startstadt
  sowie verpflichtende Latitude und Longitude.
- Reisen können mehrere Empfänger haben; Empfänger sind jeweils einer Reise
  zugeordnet.
- Angebote werden je Reise dauerhaft zugeordnet und mit eigenem
  Benachrichtigungsstatus behandelt.
- Die Distanz ist die Luftlinienentfernung zwischen Angebotsstart und
  Reise-Startort.
- E-Mails führen neue Angebote vor allen aktuell verfügbaren Angeboten auf;
  die zweite Liste enthält auch die neuen Angebote und ist nach Distanz
  aufsteigend sortiert.
- Versand erfolgt nur an Empfänger der jeweiligen Reise, über ein separates
  Gmail-Konto per SMTP mit App-Passwort.
- Jede neue Funktion benötigt Unit-Tests; ein hermetischer E2E-Test deckt den
  vollständigen Ablauf ab.

## 3. Architekturübersicht

Der Ablauf wird in fünf getrennte Verantwortungsbereiche gegliedert:

1. **Verwaltung:** Die CLI validiert Eingaben und übergibt Reise- und
   Empfängeroperationen an einen Verwaltungsservice.
2. **Persistenz:** Repositorys kapseln SQLite-Zugriffe und bewahren die
   fachlichen Beziehungen zwischen Reisen, Empfängern, Angeboten und
   Reise-Angebot-Zuordnungen.
3. **Polling und Synchronisierung:** Ein Orchestrator iteriert über Reisen,
   ruft die Movacar-API auf und synchronisiert die erhaltenen Angebote
   atomar mit dem jeweiligen Reisekontext.
4. **Bewertung und Benachrichtigung:** Ein Distanzdienst bewertet
   Reise-Angebot-Zuordnungen; ein E-Mail-Composer erzeugt daraus den
   reisespezifischen Inhalt; ein Mailer übergibt diesen an SMTP.
5. **Konfiguration und externe Adapter:** Konfiguration liefert
   Versandparameter. Adapter bilden Movacar und SMTP ab. OpenStreetMap wird
   als optional abgrenzbarer Adapter dokumentiert, aber im Standardablauf
   wegen der verpflichtenden Koordinaten nicht aufgerufen.

Die Orchestrierung hängt von Schnittstellen ab, nicht von konkreten
HTTP-/SMTP-Implementierungen. Dadurch bleiben externe Dienste in Unit- und
E2E-Tests austauschbar.

## 4. Datenmodell und Migrationsstrategie

### 4.1 Fachliche Entitäten

| Entität | Zweck | Wesentliche Daten |
|---|---|---|
| `trips` | Konfiguration einer beabsichtigten Fahrt | stabile ID, Name, Pick-up-Beginn/-Ende, Startstadt, Latitude, Longitude, Zeitstempel |
| `trip_recipients` | Empfängerzuordnung einer Reise | stabile ID oder zusammengesetzter Schlüssel aus Reise-ID und normalisierter E-Mail-Adresse |
| `offers` | Globale, deduplizierte Repräsentation eines Movacar-Angebots | Movacar-Angebots-ID als fachlich eindeutiger Schlüssel, Angebotsdaten einschließlich Startposition und zuletzt beobachteter Daten |
| `trip_offers` | Persistenter Kontext eines Angebots für genau eine Reise | Reise-ID, Angebots-ID, berechnete Distanz, Verfügbarkeit, erstmals/zuletzt gesehen, Benachrichtigungsstatus und Versandzeitpunkt |

`trip_offers` ist die maßgebliche Zuordnung. Sie erlaubt, dass dieselbe
Movacar-Angebots-ID in mehreren Reisen vorkommt und für jede Reise unabhängig
als neu erkannt, bewertet, verfügbar gehalten und versendet wird.

### 4.2 Integrität und Zustandsmodell

- Ein Angebot ist durch seine Movacar-ID global eindeutig.
- Eine Reise-Angebot-Zuordnung ist durch `(trip_id, offer_id)` eindeutig.
- Empfänger werden innerhalb einer Reise nach normalisierter E-Mail-Adresse
  eindeutig gehalten.
- Neue Zuordnungen erhalten einen unversendeten Neuheitsstatus.
- Der Versandstatus wird erst nach erfolgreichem SMTP-Versand persistiert.
  Fehlgeschlagene Zustellungen bleiben damit erneut zustellbar.
- Nach einer erfolgreichen, vollständigen API-Antwort werden alle für diese
  Reise nicht gelieferten Zuordnungen als nicht verfügbar markiert. Sie
  erscheinen nicht mehr im Abschnitt der aktuell verfügbaren Angebote.
- Schlägt eine Reiseabfrage fehl, verändert sie keine bestehende
  Verfügbarkeitsmarkierung dieser Reise.

### 4.3 Migration

Die Schemaänderung erfolgt additiv über eine versionierte, transaktionale
Migration. Sie erstellt die neuen Tabellen, Fremdschlüssel, Eindeutigkeits-
und Abfrageindizes, ohne vorhandene Angebotsdaten zu verwerfen. Die Migration
muss wiederholbar ausgeführt werden können und eine bereits migrierte
Datenbank unverändert lassen. Sofern bestehende Angebotsdaten weiterverwendbar
sind, wird deren Movacar-ID in die neue globale Angebotsidentität überführt;
eine fehlende sichere Zuordnung zu einer Reise wird nicht erfunden.

## 5. Modul- und Komponentendesign

| Komponente | Verantwortung | Abhängigkeiten |
|---|---|---|
| Reiseverwaltung | Reisen und Empfänger anlegen, löschen, hinzufügen und entfernen | Validatoren, Reise- und Empfänger-Repository |
| Verwaltungs-CLI | Unterbefehle, Argumentparsing, Darstellung und Exit-Codes | Reiseverwaltung |
| Polling-Orchestrator | Alle Reisen laden und pro Reise den Ablauf steuern | Reise-Repository, Movacar-Client, Synchronisierer, Benachrichtigungsservice |
| Movacar-Client | Reisezeitraum in API-Parameter übersetzen und Angebote liefern | HTTP-Transport, Konfiguration |
| Angebots-Synchronisierer | Globale Angebote upserten sowie Reise-Angebot-Zuordnungen und Verfügbarkeit aktualisieren | Angebots- und Zuordnungs-Repository |
| Distanzdienst | Haversine-Distanz berechnen und die Zuordnung bewerten | Reise- und Angebotskoordinaten |
| Benachrichtigungsservice | Neue und verfügbare Angebote ermitteln, sortieren, versenden und Status aktualisieren | Zuordnungs-Repository, E-Mail-Composer, Mailer |
| E-Mail-Composer | Reiseinformationen, Distanz und Highlighting in das Template übertragen | Angebotsansicht, Reiseansicht |
| SMTP-Mailer | Nachricht über Gmail SMTP ausliefern | Mail-Konfiguration, SMTP-Transport |
| Konfigurationsmodul | Nicht geheime Laufzeitoptionen und geheime Versandwerte laden und validieren | Umgebungsvariablen/lokale Konfiguration |

## 6. Datenflüsse

### 6.1 Verwaltungsfluss

1. Die CLI nimmt einen Unterbefehl und dessen Argumente entgegen.
2. Sie prüft erforderliche Felder, Zeitraumbildung, E-Mail-Format und
   Latitude/Longitude.
3. Der Verwaltungsservice persistiert die gewünschte Änderung über eine
   Transaktion.
4. Die CLI gibt standardmäßig eine menschenlesbare Erfolgsmeldung aus oder
   optional ein strukturiertes JSON-Ergebnis aus.
5. Ungültige Eingaben oder nicht erfüllbare Operationen liefern eine
   verständliche Fehlermeldung und einen nicht-null Exit-Code.

### 6.2 Polling-, Bewertungs- und Synchronisierungsfluss

1. Der Polling-Orchestrator lädt alle gespeicherten Reisen.
2. Für jede Reise bildet der Movacar-Client eine eigene Anfrage aus deren
   Start- und Endzeitpunkt.
3. Der Client liefert normalisierte Angebote mit Movacar-ID und
   Angebotsstartposition zurück.
4. Der Synchronisierer upsertet globale Angebote, erstellt oder aktualisiert
   Reise-Angebot-Zuordnungen und berechnet ihre Distanz.
5. Nach einer erfolgreichen vollständigen Antwort markiert der
   Synchronisierer nur für diese Reise zuvor vorhandene, nun fehlende
   Zuordnungen als nicht verfügbar.
6. Bei Fehlern vor Abschluss der Synchronisierung bleibt der bisherige
   Verfügbarkeitszustand dieser Reise unverändert und der Fehler wird
   sichtbar weitergegeben beziehungsweise protokolliert.

### 6.3 Benachrichtigungsfluss

1. Der Benachrichtigungsservice lädt die unversendeten, verfügbaren neuen
   Reise-Angebot-Zuordnungen sowie alle verfügbaren Zuordnungen der Reise.
2. Beide Mengen werden nach berechneter Distanz aufsteigend geordnet; neue
   Angebote bilden die erste Liste.
3. Der Composer ergänzt Reiseinformationen, Distanz in Kilometern mit einer
   Nachkommastelle und die passende Highlighting-Stufe.
4. Der SMTP-Mailer versendet genau an die Empfänger der Reise.
5. Erst nach erfolgreicher Auslieferung wird der Versandstatus der in dieser
   Nachricht enthaltenen neuen Zuordnungen persistiert.

## 7. Schnittstellen und Verträge

### 7.1 Movacar-Angebotsquelle

Der Movacar-Client akzeptiert einen Reisezeitraum und gibt normalisierte
Angebote zurück. Jedes normalisierte Angebot muss eine stabile externe ID und
eine Angebotsstartposition enthalten, damit Deduplizierung und
Distanzberechnung möglich sind. Transport-, Antwort- und
Normalisierungsfehler werden als Fehler an den Orchestrator gegeben; sie
dürfen keine Verfügbarkeitsbereinigung auslösen.

### 7.2 Distanzbewertung

Der Distanzdienst akzeptiert zwei geografische Punkte mit Latitude und
Longitude. Er verwendet die Haversine-Formel, liefert Kilometerwerte und
rundet erst für die Darstellung auf eine Nachkommastelle. Die ungerundete
Berechnung ist für Sortierung und Schwellenentscheidung maßgeblich:

- unter 100 km: starke grüne Hervorhebung,
- 100 km bis unter 250 km: dezente gelbe Hervorhebung,
- ab 250 km: neutrale Darstellung.

### 7.3 OpenStreetMap-Grenze

Die Spec erlaubt die verpflichtende Koordinatenerfassung als Alternative zu
einer unzuverlässigen Ortsauflösung. Deshalb verlangt die Reiseverwaltung
Koordinaten und der produktive Ablauf ruft keinen Geocoder auf. Falls ein
Geocoding-Adapter als technische Grenze im Projekt vorhanden bleibt, ist er
vom fachlichen Ablauf entkoppelt, rate-limitiert und cachebar zu halten; er
ist nicht Voraussetzung für Reisen, Polling oder Versand.

### 7.4 SMTP-Versand

Der Mailer erhält Empfänger, Betreff und gerenderten E-Mail-Inhalt. Die
SMTP-Konfiguration umfasst Host, Port, Transportabsicherung, Benutzername
und App-Passwort. Sie wird ausschließlich aus Umgebungsvariablen oder einer
lokalen, nicht versionierten Konfiguration geladen. Produktionsversand setzt
ein separat provisioniertes Gmail-Konto mit aktivierter
App-Passwort-Voraussetzung voraus.

### 7.5 Verwaltungs-CLI

Die CLI stellt Unterbefehle für mindestens folgende Operationen bereit:

- Reise anlegen und löschen,
- Empfänger einer Reise hinzufügen und entfernen.

Erfolgreiche Befehle liefern menschenlesbare Ausgabe; ein optionaler
JSON-Modus liefert maschinenlesbare Ergebnisse. Fehlende Reisen, doppelte
Zuordnungen, ungültige Werte und Persistenzfehler führen zu nicht-null
Exit-Codes und eindeutigen Fehlermeldungen.

## 8. Persistenz-, Konfigurations- und Artefaktstrategie

- Die SQLite-Datei und Migrationsversionen sind die alleinige Quelle für
  persistierte Reise-, Empfänger-, Angebots- und Zustandsdaten.
- Konfiguration unterscheidet versionierbare Parameter von Geheimnissen.
  Geheimnisse, insbesondere das Gmail-App-Passwort, werden weder in
  Quellcode noch in Beispieldateien gespeichert.
- Dokumentation beschreibt die Einrichtung des separaten Gmail-Kontos,
  erforderliche Konfigurationsnamen, CLI-Nutzung und das Koordinatenformat.
- E-Mail-Templates werden als versionierte Projektartefakte gepflegt und
  erhalten alle Daten über eine klar definierte Template-Ansicht, nicht über
  Datenbankzugriffe im Template.

## 9. Teststrategie

### 9.1 Unit-Tests

Unit-Tests decken mindestens ab:

- Validierung von Reisezeitraum, E-Mail-Adressen und Koordinaten,
- Repository-Integrität und Zuordnungszustände,
- Haversine-Berechnung, Rundung, Sortierung und Schwellenklassifikation,
- Synchronisierung bei neuen, bekannten, fehlenden und mehrfach zugeordneten
  Angeboten,
- Versandstatus nur nach erfolgreichem Versand,
- E-Mail-Reihenfolge, Reiseinformationen und alle Highlighting-Stufen,
- CLI-Erfolgsausgaben, JSON-Ausgabe und Fehler-Exit-Codes,
- Konfigurationsvalidierung für SMTP.

### 9.2 E2E-Test

Ein hermetischer E2E-Test verwendet eine isolierte SQLite-Datenbank und
Test-Doubles für Movacar, SMTP sowie gegebenenfalls die abgegrenzte
Geocoding-Schnittstelle. Der Test legt mehrere Reisen mit unterschiedlichen
Zeiträumen, Koordinaten und Empfängern an; simuliert Angebotsantworten;
prüft die reisespezifischen Requests, Zuordnungen, Verfügbarkeit, Distanzen,
E-Mail-Inhalte und Empfänger; und bestätigt das einmalige Setzen des
Versandstatus nach erfolgreichem Fake-SMTP-Versand. Kein automatisierter Test
kontaktiert ein echtes Gmail-Konto oder einen externen Dienst.

## 10. Abhängigkeiten und Tooling

- **SQLite:** bestehende lokale Datenbank und der bereits verwendete
  Migrationsmechanismus, erweitert um versionierte Transaktionsmigrationen.
- **Movacar:** bestehende kompatible API und deren Client-/HTTP-Mechanismus.
- **Gmail SMTP:** separates Konto, SMTP-Zugang und App-Passwort als externe
  Betriebsabhängigkeit.
- **OpenStreetMap:** keine produktive Laufzeitabhängigkeit bei verpflichtend
  erfassten Koordinaten; optional nur als gekapselte künftige Integration.
- **Tests:** bestehendes Testframework und dessen Stubbing-/Mocking-Mittel;
  keine echten externen Netzwerkzugriffe im E2E-Test.

## 11. Annahmenprotokoll und Risiken

| Annahme | Begründung | Auswirkung bei Abweichung |
|---|---|---|
| Migrationen können additiv und transaktional ausgeführt werden. | Bestehende Daten müssen erhalten bleiben. | Der Migrationsweg muss an das tatsächlich verfügbare Datenbanktool angepasst werden. |
| Die Movacar-Antwort enthält eine stabile Angebots-ID und Startkoordinaten oder ausreichend Daten zu ihrer verlässlichen Bestimmung. | Globale Deduplizierung und Distanzberechnung hängen davon ab. | Der Adapter muss eine alternative, dokumentierte Identitäts-/Positionsstrategie bereitstellen. |
| Eingaben für Reisen können Koordinaten direkt liefern. | Dies ist die bestätigte Strategie gegen unsicheres Geocoding. | Die CLI- und Verwaltungsverträge müssen erweitert werden. |
| Ein fehlgeschlagener SMTP-Versand ist eindeutig erkennbar. | Der Versandstatus darf nur nach Erfolg gespeichert werden. | Idempotenz und Wiederholungslogik müssen genauer festgelegt werden. |
| Das separate Gmail-Konto wird außerhalb des Repositories provisioniert. | Es ist eine explizite externe Abhängigkeit der Spec. | Produktivversand bleibt bis zur Provisionierung blockiert; Tests bleiben hermetisch ausführbar. |

Hauptrisiken bleiben unvollständige oder instabile Movacar-Daten sowie die
externe Provisionierung des Gmail-Kontos. Die Reise-Angebot-Zuordnung und die
Regel, Verfügbarkeit nur nach erfolgreichem Poll zu ändern, mindern das Risiko
von Doppelbenachrichtigungen und fälschlich entfernten Angeboten.

## 12. Aus der Spec übernommene und konkretisierte offene Punkte

| Spec-Offenpunkt | Planentscheidung |
|---|---|
| Tabellen, Schlüssel und Migration | `trips`, `trip_recipients`, `offers`, `trip_offers`; globale Movacar-ID und eindeutige Reise-Angebot-Zuordnung; additive transaktionale Migration |
| Angebot-zu-Reise-Lebenszyklus | Globale Angebote, pro Reise eigene persistente Zuordnung, Verfügbarkeit und Versandstatus |
| Ortsauflösung | Koordinaten je Reise verpflichtend; OpenStreetMap nicht im Standard-Laufzeitpfad |
| Distanz | Haversine in km, Darstellung mit einer Nachkommastelle |
| Highlighting | Grün unter 100 km, gelb von 100 bis unter 250 km, sonst neutral |
| Verwaltungswerkzeug | Unterbefehls-CLI, lesbare Ausgabe plus optional JSON, nicht-null Fehlercode |
| Gmail | SMTP, separates Konto, App-Passwort, Geheimnisse außerhalb des Quellcodes |
| E2E | Hermetisch mit Test-Doubles, keine externen Live-Dienste |

## 13. Explizite Nichtbestandteile

Nicht Teil dieses Plans oder Zyklus sind:

- neue Produktfunktionen außerhalb der Anforderungen von `spec_v2.0.md`,
- Übernahme früherer SDD-Architekturentscheidungen, Metriken oder
  Datenzuordnungen,
- automatische Geocoding-Auflösung als Voraussetzung für die Reiseanlage,
- reale Gmail-/Movacar-/OpenStreetMap-Aufrufe im automatisierten E2E-Test,
- Aufteilung dieser Planung in Implementierungsaufgaben; dies ist Gegenstand
  der TASK-Phase,
- Implementierungscode; dies ist Gegenstand der anschließenden Umsetzung.
