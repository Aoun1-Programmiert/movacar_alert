# Imoova API – Verifikationsnotiz (T07)

**Status: BLOCKIERT – Verifikation nicht durchführbar.**
**Datum: 2026-07-20**

## Ziel von T07

`SDD/tasks_v3.0.md` §T07 verlangt einen **echten, erfolgreichen Testaufruf**
gegen die reale Imoova-API (Endpunkt `relocations/{area}`, Parameter
`earliest_departure`) und die vollständige Dokumentation des Antwortformats
für Route, Zeitraum, Preis, Verfügbarkeit und Koordinaten. Dieses Ergebnis ist
laut Plan die verbindliche Grundlage für T09 (Imoova-Parser) und blockiert
diesen ausdrücklich (`SDD/tasks_v3.0.md` §4, §6; `plan_v3.0.md` §11.3).

## Warum die Aufgabe blockiert ist

Der Testaufruf lässt sich mit den im Zyklus vorliegenden Informationen nicht
durchführen. In `SDD/` und im gesamten Repository fehlen:

1. **Konkrete Basis-URL.** `plan_v3.0.md` §2/§7.1 dokumentiert ausschließlich
   das URL-*Muster* `{imoova_api_url}/relocations/{area}?earliest_departure={date}`.
   `{imoova_api_url}` bleibt ein Platzhalter; ein realer Host/Wert für
   `IMOOVA_API_URL` ist nirgends angegeben.
2. **Kein `curl`-Befehl.** Es existiert kein abrufbereiter Beispielaufruf.
3. **Kein Antwortformat / keine Beispielantwort.** Feldnamen, Verschachtelung,
   Einheiten und Koordinatengenauigkeit sind in `plan_v3.0.md` §7.2 und §11.3
   explizit als **offen** und „vor der TASK-Phase per direktem Testaufruf zu
   verifizieren“ markiert. Genau dieser Testaufruf ist der Gegenstand von T07.
4. **Kein `spec_v3.0.md`.** Die in `tasks_v3.0.md` §1 referenzierte
   Validierungsquelle `SDD/spec_v3.0.md` ist im Repository nicht vorhanden.

Ein Aufruf gegen die echte API würde eine erfundene Basis-URL bzw. ein
angenommenes Antwortformat voraussetzen. Das widerspricht sowohl dem
Aufgabenvertrag von T07 (realer, verifizierter Aufruf) als auch der
ausdrücklichen Vorgabe, an dieser Stelle **nicht mit Annahmen fortzufahren**.

## Auswirkung auf die weitere Task-Reihenfolge

- **T09** (Imoova-Parser) ist laut Plan/Tasks ohne T07 nicht final
  spezifizierbar und daher ebenfalls blockiert.
- **T17, T19, T20, T21** hängen (transitiv) von T08/T09 ab und sind damit
  ebenfalls betroffen.
- Die Aufgaben **T08** (Imoova-Client, Request-Bildung), **T16** (Settings),
  **T18** (CLI) hängen formal nicht vom Antwortformat ab, würden aber die
  streng sequenzielle Bearbeitungsreihenfolge überspringen; sie wurden daher
  bewusst **nicht** vorgezogen.

## Was zum Entblocken benötigt wird

Damit T07 (und in der Folge T09 ff.) fortgesetzt werden kann, ist mindestens
erforderlich:

1. Die konkrete Basis-URL der Imoova-API (`IMOOVA_API_URL`).
2. Ein funktionierender Beispielaufruf (`curl`) mit gültiger Area und gültigem
   Datum.
3. Eine reale Beispielantwort, aus der die Zielfelder gemäß `plan_v3.0.md`
   §7.2 (Route, Zeitraum, Preis, Verfügbarkeit, Ursprungs-/Zielkoordinaten)
   eindeutig ableitbar sind.

Bis diese Angaben vorliegen, bleibt der Imoova-Abruf- und Parser-Pfad
unimplementiert. Alle anbieterunabhängigen Grundlagen (Domänenmodell, Schema,
ID-Namensraum, Areal-Konfiguration, Resolver, OSM-Skript – T01–T06) sind
umgesetzt und getestet.
