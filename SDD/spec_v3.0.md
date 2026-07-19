# Spezifikation v3.0: Zusätzlicher Anbieter (Imoova) und anbieterspezifischer Versand

## 1. Dokumentstatus und Zykluskontext

**Status:** Entwurf
**Datum:** 2026-07-19
**SDD-Phase:** SPEC

Diese Spezifikation definiert einen neuen SDD-Zyklus ab einem neuen Entscheidungspunkt. Frühere SDD-Spezifikationen, -Pläne und -Tasks (siehe `SDD/v1/` und `SDD/v2/`) sind für diesen Zyklus nicht maßgeblich. Die bestehende, reise-basierte Anwendung aus Zyklus v2 bildet lediglich die technische Grundlage; Architekturentscheidungen werden nur nach den Anforderungen dieses Dokuments getroffen.

In diesem Zyklus werden ausschließlich die drei SDD-Dokumente (SPEC, PLAN, TASKS) erarbeitet. Die Implementierung ist ausdrücklich nicht Bestandteil dieses Zyklus und folgt erst nach Freigabe der TASK-Phase in einem gesonderten Schritt.

## 2. Zielsetzung

Movacar Alert soll pro Reise mehr als eine Angebotsquelle unterstützen können. Neben der bestehenden Movacar-kompatiblen API wird der Fahrzeug-Relocation-Anbieter **Imoova** als zweite, unabhängige Angebotsquelle angebunden. Für jede Reise wird konfigurierbar, welche der beiden Anbieter nach Angeboten durchsucht werden sollen. Angebote und Benachrichtigungen werden dabei je Anbieter getrennt behandelt, damit Empfänger klar erkennen, aus welcher Quelle ein Angebot stammt.

## 3. Ausgangslage und verbindlicher Umfang

Der Umfang dieses Zyklus umfasst sämtliche zum Zyklusbeginn offenen Punkte:

1. Einführung eines Anbieter-Konzepts: Jede Reise erhält eine Zuordnung zu einem oder mehreren unterstützten Anbietern (zu Zyklusbeginn: `movacar` und `imoova`).
2. Anbindung der Imoova-API als zweite Angebotsquelle, analog zur bestehenden Movacar-Integration.
3. Auflösung des von Imoova erwarteten Gebiets-/Ortsparameters ("Area") aus der in der Reise hinterlegten Startstadt, auf Basis einer vorab mit OpenStreetMap berechneten und in der Datenbank hinterlegten Zuordnungstabelle.
4. Anpassung des Polling-Ablaufs, sodass für jede Reise pro konfiguriertem Anbieter eine eigene Anfrage gestellt wird.
5. Anbieterspezifischer E-Mail-Versand: Sowohl Sofortbenachrichtigungen über neue Angebote als auch die geplanten Übersichten um 09:00 und 21:00 Uhr werden pro Anbieter in getrennten E-Mails versendet, nicht anbieterübergreifend gebündelt.
6. Behebung des bestehenden Fehlers, wonach der in Angebots-E-Mails angezeigte Link zeitweise auf ein Quellverzeichnis statt auf die tatsächlich für die Angebotsabfrage genutzte GET-Anfrage-URL verweist.

## 4. Ausgeschlossenes

Nicht Bestandteil dieses Zyklus sind:

- Eine vollständig generische Architektur für eine beliebige Anzahl weiterer Anbieter. Dieser Zyklus deckt ausschließlich Movacar und Imoova ab; eine Generalisierung über zwei Anbieter hinaus ist kein Ziel.
- Neue fachliche Produktfunktionen außerhalb der in Abschnitt 3 genannten Punkte.
- Die Übernahme von Architektur, Datenmodellen oder Entscheidungen aus früheren SDD-Zyklen ohne erneute Prüfung gegen diese Spezifikation.
- Die Detailplanung der Implementierung; diese erfolgt erst in der PLAN-Phase.
- Die Aufteilung der Arbeiten in umsetzbare Einzelaufgaben; diese erfolgt erst in der TASK-Phase.
- Jegliche Code-Implementierung; diese folgt erst nach Freigabe von SPEC, PLAN und TASKS.

## 5. Funktionale Anforderungen

### 5.1 Anbieterkonfiguration pro Reise

- Das System verwaltet zu Zyklusbeginn genau zwei unterstützte Anbieter: `movacar` (bestehend) und `imoova` (neu).
- Jeder Reise kann einer, mehrere oder beide Anbieter zugeordnet werden.
- Bestehende, bereits angelegte Reisen ohne explizite Anbieterzuordnung werden weiterhin ausschließlich über `movacar` abgefragt, damit sich ihr Verhalten durch diesen Zyklus nicht unangekündigt ändert.
- Das Verwaltungswerkzeug (CLI) wird um Operationen erweitert, mit denen einer Reise Anbieter zugeordnet und wieder entzogen werden können.

### 5.2 Anbieterspezifische Angebotsabfrage

- Der Polling-Ablauf verarbeitet für jede Reise jeden ihr zugeordneten Anbieter einzeln und fehlerisoliert; der Fehlschlag eines Anbieters darf die Verarbeitung der übrigen Anbieter und Reisen nicht verhindern.
- Für den Anbieter Imoova stellt das System eine eigene Anfrage an dessen Angebots-Endpunkt, wobei der Zeitraum der Reise berücksichtigt wird.
- Da die Imoova-API einen anbieterspezifischen Gebietsparameter ("Area") anstelle eines Ortsnamens erwartet, löst das System die in der Reise hinterlegte Startstadt über eine vorab erstellte, auf OpenStreetMap basierende Zuordnungstabelle in den passenden Imoova-Area-Wert auf.
- Ist für die Startstadt einer Reise keine passende Imoova-Area hinterlegt, wird die Reise für den Anbieter Imoova nicht abgefragt; die Abfrage der übrigen zugeordneten Anbieter bleibt davon unberührt. Dieser Zustand wird nachvollziehbar protokolliert.
- Abgerufene Angebote werden eindeutig ihrem Anbieter zugeordnet, damit Zustand, Verfügbarkeit und Benachrichtigungshistorie je Anbieter unabhängig geführt werden können.

### 5.3 Anbieterspezifischer Benachrichtigungsversand

- Neue Angebote werden weiterhin sofort gemeldet; die Sofortmail listet ausschließlich die Angebote eines einzelnen Anbieters für eine Reise.
- Sind für dieselbe Reise gleichzeitig neue Angebote mehrerer Anbieter vorhanden, werden entsprechend mehrere, getrennte Sofortmails versendet statt einer gemeinsamen Mail.
- Die geplanten Übersichten um 09:00 und 21:00 Uhr (Zeitzone `Europe/Berlin`) werden ebenfalls je Anbieter getrennt versendet; eine Übersichtsmail zeigt ausschließlich die aktuell verfügbaren Angebote eines Anbieters für die jeweilige Reise.
- Jede E-Mail zeigt weiterhin erkennbar, zu welcher Reise und zu welchem Anbieter die aufgeführten Angebote gehören.
- Distanzberechnung und -Highlighting (unter 100 km, 100 bis unter 250 km, 250 bis unter 500 km, ab 500 km) gelten unverändert für Angebote jedes Anbieters, sofern dessen Antwort die dafür notwendigen Ortsangaben liefert.
- Versandempfänger werden weiterhin ausschließlich aus der Empfängerkonfiguration der jeweiligen Reise bestimmt, unabhängig vom Anbieter.

### 5.4 Korrekter Angebots-Link in E-Mails

- Der in jeder Angebots-E-Mail angezeigte Link muss exakt der URL entsprechen, die für die zugrunde liegende GET-Anfrage der Angebotsabfrage der jeweiligen Reise und des jeweiligen Anbieters tatsächlich verwendet wurde.
- Insbesondere darf der Link nicht auf ein Quellverzeichnis oder eine andere, von der tatsächlichen Abfrage abweichende Adresse verweisen.
- Diese Anforderung gilt für Movacar unverändert fort und gilt für Imoova von Beginn an.

## 6. Daten, Integrationen und technische Leitplanken

- Die bestehende technische Grundlage aus Zyklus v2 wird weiterverwendet und darf zur Erfüllung dieser Spezifikation architektonisch erweitert oder umgestaltet werden.
- Die lokale SQLite-Datenbank bleibt die Persistenz für Reise-, Empfänger-, Anbieter-, Angebots- und Area-Zuordnungsdaten.
- Die bestehende Movacar-kompatible API bleibt unverändert eine Angebotsquelle.
- Die Imoova-API (`https://www.imoova.com/relocations/...`, exakter Endpunkt und Antwortformat noch zu verifizieren) wird als zweite Angebotsquelle angebunden.
- OpenStreetMap wird für die einmalige beziehungsweise wiederholbare Berechnung der Imoova-Area-Zuordnungstabelle verwendet; diese Berechnung erfolgt über ein separates Skript und nicht während des laufenden Pollings.
- Gmail/SMTP bleibt unverändert der Versandweg für alle E-Mails, unabhängig vom Anbieter.
- Für jede neu hinzugefügte Funktion sind Unit-Tests zu erstellen.
- Nach Abschluss der Umsetzung ist ein vollständiger E2E-Test bereitzustellen, der die neuen Funktionen (Mehr-Anbieter-Polling, Area-Auflösung, getrennter Versand, Link-Fix) gemeinsam abdeckt.

## 7. Erwartete Artefakte

Der Zyklus liefert:

1. Ein aktualisiertes SQLite-Schema einschließlich eines sicheren Migrationswegs für Anbieterzuordnungen und die Imoova-Area-Zuordnungstabelle.
2. Die erforderlichen Konfigurationsänderungen für die Anbindung der Imoova-API.
3. Ein eigenständiges, wiederholbar ausführbares Skript zur Berechnung der Imoova-Area-Zuordnungstabelle auf Basis von OpenStreetMap.
4. Erweiterte Verwaltungsoperationen (CLI) zum Zuordnen und Entziehen von Anbietern je Reise.
5. Angepasste E-Mail-Templates für anbieterspezifische Sofort- und Übersichtsmails sowie den korrigierten Angebots-Link.
6. Aktualisierte Projektdokumentation für Anbieterkonfiguration, Imoova-Einrichtung und Nutzung der erweiterten Verwaltungsoperationen.
7. Unit-Tests für jede neue Funktion.
8. Einen vollständigen E2E-Test für den anbieterübergreifenden Ablauf.

## 8. Qualitäts- und Abnahmekriterien

Die Umsetzung ist abnahmefähig, wenn:

1. Einer Reise wahlweise `movacar`, `imoova` oder beide Anbieter zugeordnet werden können und dies dauerhaft gespeichert wird.
2. Bestehende Reisen ohne explizite Anbieterzuordnung weiterhin ausschließlich über Movacar abgefragt werden.
3. Der Polling-Ablauf jeden einer Reise zugeordneten Anbieter einzeln und fehlerisoliert verarbeitet.
4. Die Imoova-Area für die Startstadt einer Reise korrekt aus der OpenStreetMap-basierten Zuordnungstabelle aufgelöst wird und eine fehlende Zuordnung die Abfrage anderer Anbieter nicht beeinträchtigt.
5. Neue Angebote und geplante Übersichten für jede Reise je Anbieter in getrennten E-Mails versendet werden, niemals anbieterübergreifend in einer Mail zusammengefasst.
6. Jede Angebots-E-Mail einen Link enthält, der exakt der tatsächlich genutzten GET-Anfrage-URL entspricht, ohne Verweis auf ein Quellverzeichnis.
7. Die vorgesehenen Anbieter-Verwaltungsoperationen über das Verwaltungswerkzeug ausführbar sind.
8. Für jede neue Funktion Unit-Tests vorhanden sind und der vollständige E2E-Test den anbieterübergreifenden Ablauf erfolgreich abdeckt.

## 9. Offene Entscheidungen für die PLAN-Phase

Die folgenden Punkte sind absichtlich nicht in dieser SPEC entschieden und müssen in der PLAN-Phase konkretisiert werden:

- Exaktes Antwortformat der Imoova-API (Felder für Route, Zeitraum, Preis, Fahrzeugdaten, Verfügbarkeit) sowie der genaue Endpunkt, die zulässigen Query-Parameter und das Zeitraum-Format; dies erfordert eigene Recherche, unter anderem mittels direkter Testaufrufe.
- Exakte Tabellenstruktur, Schlüssel und Migration für Anbieterzuordnungen, anbieterspezifische Angebote und die Imoova-Area-Zuordnungstabelle.
- Herkunft, Format und Pflegeprozess der Liste der Imoova-Areas, die dem OpenStreetMap-Berechnungsskript als Grundlage dient.
- Genaues Verfahren, mit dem das OpenStreetMap-Berechnungsskript eine Reise-Startstadt einer Imoova-Area zuordnet, einschließlich Umgang mit Mehrdeutigkeiten oder fehlenden Treffern.
- Modell und Lebenszyklus anbieterspezifischer Angebote, insbesondere ob und wie sich Angebots-IDs zwischen Movacar und Imoova unterscheiden oder überschneiden können.
- Ob und wie die bestehende Distanzberechnung und das Highlighting unverändert auf Imoova-Angebote angewendet werden können, abhängig von den tatsächlich verfügbaren Ortsangaben der Imoova-Antwort.
- Konkrete Fehlerursache und technischer Fix für den Quellverzeichnis-Link-Fehler, einschließlich Nachweis, dass der bestehende Code-Pfad (`build_trip_url`) diesen Fehler tatsächlich reproduziert oder ob die Ursache an anderer Stelle liegt.
- Authentifizierung, Rate-Limits, Timeout- und Retry-Verhalten für die Imoova-API.
- Ausgestaltung der erweiterten Verwaltungs-CLI-Befehle für Anbieterzuordnungen.
- Umfang und technische Ausführung des E2E-Tests, einschließlich der Test-Doubles für die Imoova-API.

## 10. Annahmen und Risiken

### Annahmen

- Imoova ist, wie Movacar, ein Marktplatz für Fahrzeug-Relocations und liefert Angebote mit vergleichbaren fachlichen Grundgrößen (Route, Zeitraum, ggf. Preis); die exakte technische Vergleichbarkeit der Antwortdaten wird erst in der PLAN-Phase verifiziert.
- Für die betroffenen Reise-Startstädte lässt sich über OpenStreetMap eine hinreichend eindeutige Imoova-Area ermitteln, sobald eine Liste gültiger Areas vorliegt.
- Der bestehende Code-Pfad zur Link-Erzeugung (`build_trip_url` in `src/api/api_client.py` beziehungsweise dessen Verwendung in `src/loop/poll_loop.py`) deckt den gemeldeten Fehler nicht vollständig ab oder der Fehler tritt in einem anderen, noch zu identifizierenden Pfad auf.

### Risiken

- Die Imoova-API-Struktur ist zu Zyklusbeginn nicht verifiziert; abweichende oder fehlende Ortsangaben in Imoova-Angeboten können Distanzberechnung und Highlighting für diesen Anbieter einschränken.
- Eine unvollständige oder veraltete Areas-Liste kann dazu führen, dass einzelne Reise-Startstädte keiner Imoova-Area zugeordnet werden können und der Anbieter für diese Reisen faktisch nicht nutzbar ist.
- Die getrennte Versendung je Anbieter erhöht die Anzahl der versendeten E-Mails je Reise; bei vielen aktiven Anbietern und Reisen steigt das SMTP-Versandvolumen entsprechend.
- Ohne verifizierte Reproduktion kann der Link-Fehler in der PLAN-Phase eine andere Ursache haben als vermutet, was die vorgesehene Lösung beeinflusst.
