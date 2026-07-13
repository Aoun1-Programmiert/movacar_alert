# Spezifikation: API-Monitor & Mail-Notifier (spec_v1.md)

## 1. Zweck & Hauptziel

Das Programm dient der automatisierten, regelmäßigen Überwachung einer spezifischen, öffentlich zugänglichen API auf neue Fahrzeug- oder Reiseangebote. Ziel ist es, den Nutzer zeitnah per E-Mail zu benachrichtigen, sobald neue Angebote verfügbar sind, und gleichzeitig besonders attraktive Fernfahrten visuell hervorzuheben. Das Programm läuft ohne grafische Oberfläche (Headless) im Hintergrund.

---

## 2. Funktionsumfang (In-Scope)

* **Periodische API-Abfrage:** Das Programm führt in einem definierten Zeitintervall eine HTTP-GET-Anfrage an die Ziel-URL aus.
* **Daten-Parsing & Stationen-Auflösung:**
* Extraktion der Angebote aus dem `data`-Array der JSON-Antwort.


* Auflösung der Stations-IDs (`origin` und `destination`) durch Verknüpfung mit den im `included`-Array gelieferten Geodaten und Details.




* **Zustandsvergleich & Persistenz:**
* Abgleich der aktuell gefundenen Angebots-IDs mit dem in einer lokalen SQLite-Datenbank gespeicherten Zustand.


* Erkennung von *neuen* Angeboten (Sektion 1 der Mail) und *bestehenden* Angeboten (Sektion 2 der Mail).


* **E-Mail-Versand (SMTP):**
* Versand einer strukturierten E-Mail, sofern neue Angebote seit der letzten Abfrage hinzugefügt wurden.
* Die E-Mail listet oben alle neuen Angebote auf, gefolgt von einer Liste aller alten, weiterhin aktiven Angebote.


* **Highlight-Logik ("Äußerst interessant"):**
Angebote werden als "äußerst interessant" markiert und in der E-Mail visuell hervorgehoben, wenn sie **alle** folgenden Kriterien erfüllen:
1. **Dauer:** Die Differenz zwischen `end_date` und `start_date` beträgt 2 Tage oder mehr.


2. **Start:** Der Abfahrtsort (`origin`) liegt geografisch innerhalb der Landesgrenzen von Deutschland.


3. **Ziel:** Der Ankunftsort (`destination`) liegt geografisch außerhalb der Landesgrenzen von Deutschland.





---

## 3. Nicht-Ziele (Out-of-Scope)

* Keine Benutzeroberfläche (weder Web-UI noch Desktop-GUI).
* Kein Cloud-Hosting oder permanente Server-Infrastruktur im aktuellen Scope.
* Keine Authentifizierungs-Logik (z. B. Bearer-Token-Erneuerung), da die API nachweislich ungeschützt öffentlich aufrufbar ist.
* Keine Verwaltung mehrerer Empfänger-E-Mails über eine UI.

---

## 4. Datenmodell & Logik

### API-Relevante Felder



* `id`: Eindeutiger Identifikator des Angebots (z. B. `"252266_202065_202066"`).
* `start_date` / `end_date`: Start- und Endzeitpunkt der Fahrt.
* `free_km`: Inkludierte Freikilometer.
* `relationships`: Enthält die IDs für `origin` und `destination`.
* `included`: Enthält die Details zu den Stationen (`city`, `latitude`, `longitude`).

### SQLite-Datenbankstruktur

Es wird eine minimale, lokale Tabelle zur Zustandserhaltung benötigt:

* `offers`: `id` (Primary Key), `start_date`, `end_date`, `origin_city`, `destination_city`, `first_seen_timestamp`.

### Logischer Ablauf der Erkennung

1. **Neu:** Eine Angebots-ID ist in der API-Antwort, aber *nicht* in der SQLite-Datenbank vorhanden. -> *Wird in Sektion 1 der Mail aufgenommen und in die DB eingetragen.*
2. **Bestehend (Alt):** Eine Angebots-ID ist in der API-Antwort *und* bereits in der SQLite-Datenbank vorhanden. -> *Wird in Sektion 2 der Mail aufgenommen.*
3. **Gelöscht/Abgelaufen:** Eine ID ist in der SQLite-Datenbank, taucht aber *nicht mehr* in der API-Antwort auf. -> *Wird aus der SQLite-Datenbank entfernt (Bereinigung).*

---

## 5. System- & Nutzungsflow

```
[ Start / Wakeup ]
        │
        ▼
[ HTTP GET an API ]
        │
        ▼
[ JSON extrahieren & Stationen via enthaltene IDs auflösen ]
        │
        ▼
[ Geo-Check (DE vs. Ausland) & Zeit-Check für Highlight-Logik ]
        │
        ▼
[ Abgleich mit SQLite-Datenbank ]
        │
 ┌──────┴────────────────────────────────────────┐
 │                                               │
 ▼ (Keine neuen Angebote vorhanden)               ▼ (Mind. 1 neues Angebot gefunden)
[ DB bereinigen für gelöschte Einträge ]        [ E-Mail generieren & via SMTP senden ]
        │                                                │
        │                                                ▼
        │                                       [ Neue IDs in SQLite speichern ]
        │                                                │
        └───────────────────────┬────────────────────────┘
                                │
                                ▼
                       [ Sleep-Intervall ]

```

---

## 6. Constraints & Technische Einschränkungen

* **Geodaten-Validierung:** Die Prüfung, ob `origin` in Deutschland liegt und `destination` außerhalb, erfolgt mathematisch/logisch über die vom API-Server gelieferten Koordinaten (`latitude`/`longitude`). Es wird ein vordefiniertes Koordinaten-Rechteck (Bounding Box) für die Grenzen Deutschlands hinterlegt.


* **Plattform:** Das Programm muss ressourcensparend im Hintergrund auf einem lokalen Rechner (Laptop) ausführbar sein.
* **Datenspeicherung:** Die Speicherung des Zustands erfolgt ausschließlich dateibasiert (SQLite), um einen Datenverlust bei System-Standby oder Skript-Neustarts zu verhindern.

---

## 7. Edge Cases & Fehlertoleranz

* **Laptop-Standby / Ruhezustand:** Wird der Laptop zugeklappt, pausiert das Programm. Nach dem Aufwachen wird der Zyklus beim nächsten regulären Intervall-Trigger fortgesetzt. SQLite sorgt dafür, dass keine doppelten Mails für bereits bekannte Angebote gesendet werden.
* **Netzwerk-Timeout / API offline:** Schlägt der HTTP-Aufruf fehl (z. B. keine Internetverbindung), bricht das Skript nicht ab. Der Fehler wird abgefangen, intern vermerkt und das Skript wartet auf das nächste Abfrageintervall.
* **Fehlgeschlagener Mail-Versand:** Kann die SMTP-Verbindung nicht aufgebaut werden, wird der Datenbank-Eintrag für die "neuen" Angebote *nicht* vorgenommen. Dadurch werden sie beim nächsten erfolgreichen Durchlauf erneut als "neu" erkannt und zugestellt.

---

## 8. Erfolgskriterien

* Das Skript läuft stabil in einer Endlosschleife, ohne bei Verbindungsabbrüchen abzustürzen.
* Bei Erscheinen eines neuen Angebots wird genau *eine* E-Mail ausgelöst.
* Angebote, die die Kriterien (DE $\rightarrow$ Ausland, $\ge 2$ Tage) erfüllen, sind in der E-Mail unübersehbar hervorgehoben.



---

## 9. Offene Punkte / Konfiguration (In der Umsetzungsphase zu definieren)

* Festlegung des konkreten Abfrage-Intervalls (z. B. alle 15, 30 oder 60 Minuten).
* Definition der genauen E-Mail-Struktur (Text-Format oder einfaches HTML für das Highlighting).
* Hinterlegen der SMTP-Zugangsdaten und der Ziel-E-Mail-Adresse über eine externe Konfigurationsdatei.