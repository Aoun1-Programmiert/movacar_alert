# Movacar Alert

## Nächste Schritte

Ich möchte das CLI-Script zum Erstellen von Reisen per API ansprechbar machen
diese API soll dann über eine bereitgestellte Website Aufrufbar sein
diese Website soll dann die Möglichkeit bieten, Reisen anzulegen, zu löschen und Empfänger zu verwalten

darüber hinaus möchte ich alle Städte, die über eine Reise angelegt werden sowie alle Städte, die in Angeboten aufgelistet werden, 
in einer SQL Tabelle abspeichern (Name, Koordinaten, Land)
- das Land soll über die Koordinate bestimmt werden (Welche API kann ich dafür nutzen? OpenStreetMap Nominatim? Google Maps API?)
- dieses Land dann im ISO Format abspeichern (z.B. DE, AT, CH)
- auf der Website soll es dann möglich sein, beim Anlegen der Stadt für die Reise vorschläge zu bekommen, 
welche Städte bereits in der Datenbank vorhanden sind (Autocomplete)

## Überblick

Movacar Alert überwacht die konfigurierte Movacar-API fortlaufend auf Angebote und informiert per E-Mail über neue Einträge. Bereits bekannte Angebote werden in einer lokalen SQLite-Datenbank gespeichert, damit nach Neustarts keine doppelten Benachrichtigungen entstehen.

E-Mails zeigen die Reiseinformationen und sortieren die verfügbaren Angebote nach
der Entfernung zur Startstadt. Angebote unter 100 km werden rot, von 100 bis
unter 250 km orange, von 250 bis unter 500 km gelb und ab 500 km neutral
dargestellt. Die
Koordinaten werden bei der Reiseanlage verpflichtend angegeben; eine
Laufzeit-Geocodierung über OpenStreetMap findet nicht statt.

Pro Reise werden neue Angebote sofort und aktuelle Angebote zusätzlich täglich
um 09:00 und 21:00 Uhr (Zeitzone `Europe/Berlin`) an deren konfigurierte
Empfänger versendet. Ein gemeinsames Angebot kann deshalb in mehreren Reisen
unabhängig benachrichtigt werden.

Die API wird standardmäßig zu den vollen Viertelstunden (`00`, `15`, `30`,
`45`) abgefragt. Der erste Lauf wartet ebenfalls auf den nächsten solchen
Zeitpunkt; `POLL_INTERVAL_MINUTES=15` steuert dabei die Rasterbreite.

Wenn die API einen `base_price` liefert, wird der Preis inklusive Währung aus
der Antwort übernommen, gespeichert und in der Angebots-E-Mail angezeigt.
`amount_minor_units` wird dabei als kleinste Währungseinheit interpretiert,
also beispielsweise `100` als `1,00 EUR`.

## Funktionen

- Regelmäßige Abfrage einer frei konfigurierbaren HTTP(S)-API
- Wiederholungsversuche bei temporären API- und Netzwerkfehlern
- Auflösung von Start- und Zielstationen aus der API-Antwort
- Persistenter Angebotsstatus in SQLite
- HTML-E-Mails für neue und weiterhin verfügbare Angebote
- Tägliche Angebotsübersichten um 09:00 und 21:00 Uhr
- Optionales, rotierendes Logfile zusätzlich zur Konsolenausgabe

## Voraussetzungen

- Python 3.10 oder neuer
- Zugang zu einem SMTP-Server
- Eine Movacar-kompatible API-URL

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Unter Windows wird die virtuelle Umgebung mit `.venv\Scripts\activate` aktiviert.

## Konfiguration

Lege im Projektverzeichnis eine Datei namens `.env` an. Sie enthält lokale Zugangsdaten und wird nicht versioniert.

```dotenv
API_URL=https://example.com/api/offers
POLL_INTERVAL_MINUTES=15
SQLITE_PATH=movacar_alert.sqlite

SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=benutzer@example.com
SMTP_PASSWORD=dein-passwort
SMTP_FROM=Movacar Alert <benutzer@example.com>
SMTP_USE_TLS=true

HTTP_TIMEOUT_SECONDS=10
LOG_FILE_PATH=logs/movacar_alert.log
```

`SMTP_PASSWORD` ist das App-Passwort des separaten Gmail-Kontos, das
ausschließlich für diesen Versand verwendet wird. Aktiviere für dieses Konto
die Zwei-Faktor-Authentifizierung und erzeuge anschließend unter den
Kontosicherheitseinstellungen ein App-Passwort. Trage das App-Passwort nur
lokal in `.env` oder als Umgebungsvariable ein; verwende niemals das echte
Gmail-Passwort und committe keine Zugangsdaten.

| Variable | Erforderlich | Beschreibung |
| --- | --- | --- |
| `API_URL` | Ja | Vollständige HTTP(S)-URL der Angebots-API |
| `POLL_INTERVAL_MINUTES` | Nein | Rasterbreite der Prüfzeitpunkte in Minuten; Standard: `15` |
| `SQLITE_PATH` | Ja | Pfad zur lokalen SQLite-Datenbank |
| `SMTP_HOST` | Ja | SMTP-Server |
| `SMTP_PORT` | Ja | SMTP-Port, z. B. `587` für STARTTLS |
| `SMTP_USER` | Ja | SMTP-Benutzername |
| `SMTP_PASSWORD` | Ja | SMTP-Passwort oder App-Passwort |
| `SMTP_FROM` | Ja | Absender im Format `Anzeigename <adresse@example.com>`; ohne Anzeigename ist auch nur die Adresse möglich |
| `SMTP_USE_TLS` | Ja | `true` für STARTTLS, sonst `false` |
| `HTTP_TIMEOUT_SECONDS` | Ja | Timeout eines API-Aufrufs in Sekunden |
| `LOG_FILE_PATH` | Nein | Optionaler Pfad für ein rotierendes Logfile |

Empfänger werden ausschließlich einer Reise über die Verwaltungs-CLI
zugeordnet. Distanz-Highlighting richtet sich ausschließlich nach der
Entfernung zwischen Angebot und Startstadt der Reise: unter 100 km rot, von
100 bis unter 250 km orange, von 250 bis unter 500 km gelb, ab 500 km
neutral. Die Distanz wird als Luftlinie in
Kilometern mit einer Nachkommastelle dargestellt; Sortierung und Schwellen
verwenden den ungerundeten Wert. Die früheren Werte `SMTP_TO` und `DE_BBOX_*`
werden beim Start nur als ignorierte Legacy-Konfiguration protokolliert und
bewirken weder Versand noch Angebotsfilterung.

Umgebungsvariablen des Betriebssystems haben Vorrang vor Werten aus `.env`.

## Starten

```bash
python -m src.main
```

Das Programm führt beim Start alle ausstehenden, versionierten SQLite-Migrationen
atomar und idempotent aus und startet erst danach den Dauerbetrieb. Bereits
bekannte globale Angebote werden dabei nicht künstlich einer Reise zugeordnet;
sie können beim ersten passenden Reise-Poll eine neue reisespezifische
Zuordnung erhalten. Nicht verfügbare Reise-Angebote werden nach 14 Tagen
bereinigt, globale Angebote nur ohne verbleibende Reisezuordnung.

Gibt es keine Reisen, bleibt der Dienst aktiv, protokolliert den Leerlauf und
führt weder API- noch SMTP-Aufrufe aus. Zum Stoppen `Ctrl+C` drücken.

Bei einer Sofortmail werden zuerst die neuen Angebote und darunter alle aktuell
verfügbaren Angebote der jeweiligen Reise aufgeführt. Der Versand erfolgt nur
an deren Empfänger; erst nach erfolgreicher SMTP-Übergabe wird der
Versandstatus gespeichert. Schlägt der Versand fehl, bleiben die Angebote beim
nächsten Durchlauf erneut meldepflichtig. Übersichten werden pro Reise und
Empfängerliste versendet; ein fehlgeschlagener Übersichtsslot bleibt
wiederholbar.

## Reiseverwaltung

Reisen werden direkt in der SQLite-Datenbank verwaltet. Die CLI verwendet
`SQLITE_PATH`, wenn die Umgebungsvariable gesetzt ist; mit `--sqlite-path`
kann ein abweichender Datenbankpfad angegeben werden.

```bash
python -m src.admin_cli trip create \
  --trip-id lara-aouni-reise-2 \
  --name "Aouni & Lara - von Venedig aus weiter" \
  --pickup-start 2026-08-01 \
  --pickup-end 2026-08-05 \
  --start-city Venedig \
  --latitude 45.4387 \
  --longitude 12.3271

python -m src.admin_cli trip list
python -m src.admin_cli trip list --json
python -m src.admin_cli trip delete --trip-id sommer-2026

python -m src.admin_cli trip recipient add \
  --trip-id sommer-2026 \
  --email empfaenger@example.com
python -m src.admin_cli trip recipient list \
  --trip-id sommer-2026 \
  --json
python -m src.admin_cli trip recipient remove \
  --trip-id sommer-2026 \
  --email empfaenger@example.com
```

Alle Reiseangaben beim Anlegen sind verpflichtend. Die Textausgabe ist für
interaktive Nutzung bestimmt; `--json` gibt eine strukturierte Antwort aus.
Empfänger werden vor der Speicherung getrimmt und kleingeschrieben. Ungültige
Eingaben, doppelte Empfänger, unbekannte Reisen und Datenbankfehler enden mit
einem nicht-null Exit-Code und einer Fehlermeldung auf der
Standardfehlerausgabe. Die JSON-Ausgabe der Empfängerbefehle enthält bei
`add` und `remove` `trip_id` und `recipient`; `list` enthält `trip_id` und
das alphabetisch sortierte Array `recipients`.

## Tests

```bash
python -m pytest -q
```

## Projektstruktur

```text
src/
  api/       # HTTP-Abruf der Angebotsdaten
  config/    # Umgebungsvariablen und Zeitzonenpolitik
  loop/      # Polling-Ablauf und geplante Übersichten
  mailer/    # HTML-Templates und SMTP-Versand
  models/    # Angebotsdatenmodelle
  parser/    # Verarbeitung der API-Antwort
  storage/   # SQLite-Persistenz
tests/       # Unit- und Integrationstests
```
