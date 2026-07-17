# Spezifikation v2.0: Reise-basierte Konfiguration und Benachrichtigungen

## 1. Dokumentstatus und Zykluskontext

**Status:** Freigegeben  
**Datum:** 2026-07-15  
**SDD-Phase:** SPEC  

Diese Spezifikation definiert einen neuen SDD-Zyklus ab einem neuen Entscheidungspunkt. Frühere SDD-Spezifikationen, -Pläne und -Tasks sind für diesen Zyklus nicht maßgeblich. Die bestehende Anwendung bildet lediglich die technische Grundlage; Architekturentscheidungen werden nur nach den Anforderungen dieses Dokuments getroffen.

## 2. Zielsetzung

Movacar Alert soll durch den Datentyp **Reise** konfigurierbar werden. Eine Reise bündelt die Suchkriterien und Empfänger einer beabsichtigten Fahrt. Das System soll dadurch mehrere Reisen unabhängig verwalten, für jede Reise passende Angebote abfragen, diese räumlich bewerten und reisespezifisch per E-Mail versenden können.

## 3. Ausgangslage und verbindlicher Umfang

Der Umfang dieses Zyklus umfasst sämtliche zum Zyklusbeginn offenen Punkte:

1. Reise- und Empfängerkonfiguration durch ein persistentes Datenmodell.
2. Speicherung der Reise-Entitäten in der lokalen SQLite-Datenbank.
3. Reisespezifische Movacar-API-Abfragen mit an den Reisezeitraum angepassten Start- und Endparametern.
4. Entscheidung und Umsetzung einer Zuordnung zwischen Angeboten und Reisen.
5. Auflösung der konfigurierten Startstadt über OpenStreetMap sowie Berechnung der Luftlinienentfernung zu Angeboten.
6. Sortierung der Angebote nach Entfernung zur Startstadt.
7. Entfernungsspezifisches Highlighting für Angebote unter 100 km, von 100 bis unter 250 km sowie von 250 bis unter 500 km.
8. Anpassung der E-Mail-Templates um Reiseinformationen und Distanz-Highlighting.
9. Ein Verwaltungswerkzeug für typische Reise- und Empfängeroperationen.
10. Einrichtung und Nutzung eines separaten Gmail-Kontos für den Versand der Benachrichtigungen.

## 4. Ausgeschlossenes

Nicht Bestandteil dieses Zyklus sind:

- Neue fachliche Produktfunktionen außerhalb der oben genannten offenen Punkte.
- Die Übernahme von Architektur, Metriken oder Datenzuordnungen aus früheren SDD-Artefakten.
- Die Detailplanung der Implementierung; diese erfolgt erst in der PLAN-Phase.
- Die Aufteilung der Arbeiten in umsetzbare Einzelaufgaben; diese erfolgt erst in der TASK-Phase.

## 5. Funktionale Anforderungen

### 5.1 Reisen und Empfänger

- Das System verwaltet Reisen als eigene persistente Entität.
- Jede Reise enthält mindestens einen Namen, einen zulässigen Pick-up-Zeitraum mit Beginn und Ende sowie eine Startstadt.
- Einer Reise können eine oder mehrere Empfänger-E-Mail-Adressen zugeordnet werden.
- Reisen und Empfängerzuordnungen werden in SQLite dauerhaft gespeichert.
- Das System stellt Verwaltungsoperationen bereit, um Reisen anzulegen und zu löschen sowie Empfänger einer Reise hinzuzufügen und zu entfernen.

### 5.2 Reisespezifische Angebotsabfrage

- Der Polling-Ablauf verarbeitet jede hinterlegte Reise.
- Für jede Reise wird eine eigene Anfrage an die bestehende Movacar-kompatible API gestellt.
- Die Anfrage verwendet die Daten der jeweiligen Reise für die Start- und Endparameter des Suchzeitraums.
- Das System ordnet abgerufene und gespeicherte Angebote einer Reise zu, damit Angebote und Benachrichtigungszustände reisespezifisch behandelt werden können.

### 5.3 Räumliche Bewertung

- Das System verwendet für die Startstadt einer Reise geografische Koordinaten, die vorrangig über OpenStreetMap aufgelöst werden. Ist diese Auflösung nicht ausreichend zuverlässig, sind Längen- und Breitengrad verpflichtend für die Reise zu hinterlegen.
- Für jedes Angebot berechnet das System die Luftlinienentfernung zwischen dessen Startposition und der Startstadt der zugehörigen Reise.
- Jedes E-Mail-Template listet zuerst die neu erkannten Angebote auf.
- Neue Angebote unter 100 km, von 100 bis unter 250 km und von 250 bis unter 500 km werden unterschiedlich hervorgehoben.
- Unterhalb der neuen Angebote listet das E-Mail-Template alle aktuell verfügbaren Angebote, einschließlich der neu erkannten Angebote, aufsteigend nach ihrer Entfernung zur Startstadt der Reise auf.

### 5.4 E-Mail-Versand

- E-Mail-Templates zeigen die zugehörigen Reiseinformationen an.
- E-Mail-Templates zeigen die Distanzbewertung beziehungsweise das zugehörige Highlighting an.
- Versandempfänger werden pro Reise aus deren Empfängerkonfiguration bestimmt.
- Der Versand erfolgt über ein separates, ausschließlich für den Mailversand vorgesehenes Gmail-Konto.

## 6. Daten, Integrationen und technische Leitplanken

- Die bestehende technische Grundlage wird weiterverwendet und darf zur Erfüllung dieser Spezifikation architektonisch erweitert oder umgestaltet werden.
- Die lokale SQLite-Datenbank bleibt die Persistenz für Reise-, Empfänger- und Angebotsdaten.
- Die bestehende Movacar-kompatible API bleibt die Angebotsquelle.
- OpenStreetMap wird für die Auflösung der Startstadt verwendet.
- Gmail/SMTP wird für den Versand verwendet.
- Erforderliche Konfigurationswerte für das Versandkonto werden als Konfiguration bereitgestellt und nicht im Quellcode hinterlegt.
- Für jede neu hinzugefügte Funktion sind Unit-Tests zu erstellen.
- Nach Abschluss der Umsetzung ist ein vollständiger E2E-Test bereitzustellen, der die neuen Funktionen gemeinsam abdeckt.

## 7. Erwartete Artefakte

Der Zyklus liefert:

1. Ein aktualisiertes SQLite-Schema einschließlich eines sicheren Migrationswegs für die neuen Daten.
2. Die erforderlichen Konfigurationsänderungen für die Reise- und Versandfunktionalität.
3. Ein Verwaltungs-Skript oder eine gleichwertige CLI für Reise- und Empfängeroperationen.
4. Angepasste E-Mail-Templates mit Reiseinformationen und Distanz-Highlighting.
5. Aktualisierte Projektdokumentation für Konfiguration, Einrichtung des Versandkontos und Nutzung der Verwaltungsoperationen.
6. Unit-Tests für jede neue Funktion.
7. Einen vollständigen E2E-Test für den neuen Reise-basierten Ablauf.

## 8. Qualitäts- und Abnahmekriterien

Die Umsetzung ist abnahmefähig, wenn:

1. Mehrere Reisen mit jeweils eigenen Zeiträumen, Startstädten und Empfängern dauerhaft verwaltet werden können.
2. Der Polling-Ablauf jede gespeicherte Reise verarbeitet und dafür eine reisespezifische API-Anfrage ausführt.
3. Angebote eindeutig und dauerhaft im Kontext der jeweiligen Reise behandelt werden.
4. E-Mails zuerst neue Angebote mit sichtbarer Unterscheidung der 100-km- und 250-km-Schwellen und darunter alle verfügbaren Angebote einschließlich der neuen Angebote aufsteigend nach Distanz zur Reise-Startstadt anzeigen.
5. E-Mails die Reiseinformationen enthalten und nur an deren konfigurierte Empfänger adressiert werden.
6. Die vorgesehenen Reise- und Empfängeroperationen über das Verwaltungswerkzeug ausführbar sind.
7. Das separate Gmail-Konto für den Versand konfiguriert und dokumentiert ist.
8. Für jede neue Funktion Unit-Tests vorhanden sind und der vollständige E2E-Test den End-to-End-Ablauf erfolgreich abdeckt.

## 9. Offene Entscheidungen für die PLAN-Phase

Die folgenden Punkte sind absichtlich nicht in dieser SPEC entschieden und müssen in der PLAN-Phase konkretisiert werden:

- Exakte Tabellenstruktur, Schlüssel und Migration für Reisen, Empfänger und Angebote.
- Modell und Lebenszyklus der Angebots-zu-Reise-Zuordnung, insbesondere bei einem Angebot, das zu mehreren Reisen passt.
- Entscheidung zwischen einer OpenStreetMap-basierten Ortsauflösung und verpflichtend hinterlegten Längen- und Breitengraden je Reise sowie, bei OpenStreetMap-Nutzung, Endpunkt, Fehlerbehandlung, Rate-Limit-Strategie und Caching.
- Formel, Einheiten, Rundung und Darstellung der Luftlinienentfernung.
- Präzise Darstellung und Priorität der Highlighting-Stufen unter 100 km, von 100 bis unter 250 km, von 250 bis unter 500 km und ab 500 km.
- Ausgestaltung, Ein- und Ausgabeformate sowie Fehlerverhalten der Verwaltungs-CLI.
- Konkrete Gmail-Authentifizierung, Konto-Provisionierung und benötigte Konfigurationswerte.
- Umfang und technische Ausführung des E2E-Tests, einschließlich der Test-Doubles für externe Dienste.

## 10. Annahmen und Risiken

### Annahmen

- Mit Ausnahme der zuverlässigen Ermittlung von Längen- und Breitengraden für die konfigurierte Startstadt sind die technischen Voraussetzungen für alle Änderungen bereits vorhanden.
- Die PLAN-Phase bewertet, ob die Ortsauflösung über OpenStreetMap die fachlichen und betrieblichen Anforderungen zuverlässig erfüllt.

### Risiken

- Mehrdeutige Ortsnamen, externe Geocoding-Grenzen und unzuverlässige Ergebnisse der OpenStreetMap-Auflösung können die Distanzbewertung beeinträchtigen. Falls dieses Risiko nicht vertretbar ist, werden Längen- und Breitengrad als verpflichtende Informationen für jede Reise geführt.
- Eine falsche oder unvollständige Angebots-zu-Reise-Zuordnung kann zu Doppelbenachrichtigungen oder ausgelassenen Benachrichtigungen führen.
- Die separate Provisionierung des Gmail-Kontos ist eine externe Abhängigkeit für den produktiven Versand.
