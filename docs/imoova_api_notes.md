# Imoova API-Verifikation (T07)

## Testaufruf

Am 2026-07-23 wurde folgender erfolgreicher Live-Aufruf ausgefuehrt:

```text
GET https://www.imoova.com/relocations/europe?earliest_departure=2026-07-27
HTTP 200
Content-Type: text/html; charset=utf-8
```

Die Antwort ist 357354 Byte gross und enthaelt die Angebotsdaten
servergerendert in einem TanStack-Router-Serialisierungsblock. Sie ist keine
JSON-API-Antwort. Die Daten liegen unter:

```text
dehydratedData.dehydratedQueryClient.queries[0].state.data.pages[0]
  .relocations.data
```

Die erste Seite enthielt 18 Angebote; `paginatorInfo` wies insgesamt 19
Angebote und eine weitere Seite aus.

## Verifiziertes Angebotsformat

Jeder Eintrag in `relocations.data` ist ein `Relocation`-Objekt. Das folgende
gekürzte Beispiel zeigt alle für T09 relevanten Felder und ihre Verschachtelung:

```text
{
  __typename: "Relocation",
  id: "115053",
  reference: "RLC115053",
  name: "Madrid to Tenerife",
  status: "READY",
  type: "RELOCATION",
  count: 1,
  available_from_date: "2026-08-24",
  available_to_date: "2026-09-06",
  earliest_departure_date: "2026-08-24",
  latest_departure_date: "2026-09-05",
  currency: "EUR",
  hire_unit_type: "NIGHT",
  hire_unit_rate: 100,
  hire_units_allowed: 10,
  extra_hire_units_allowed: 3,
  extra_hire_unit_rate: 12000,
  retail_rate: null,
  booking_fee_amount: 9900,
  distance_allowed: 2294,
  measurement: "METRIC",
  departureCity: {
    name: "Madrid",
    state: "ES",
    region: "EU",
    lat: 40.4167279,
    lng: -3.7032905
  },
  deliveryCity: {
    name: "Tenerife",
    state: "ES",
    region: "EU",
    lat: 28.2915637,
    lng: -16.6291304
  },
  vehicle: {
    type: "CAMPER_VAN",
    name: "Eu Active Poptop 4 Auto Select"
  }
}
```

## Zielfelder fuer T09

| Zielfeld | Verifiziertes Feld | Format und Einheit |
| --- | --- | --- |
| Anbieterinterne ID | `id` | String; fuer `Offer.id` zwingend mit `imoova:` praefixieren. |
| Route | `departureCity.name`, `deliveryCity.name` | Zeichenketten; `name` ist nur eine Anzeigehilfe. |
| Startkoordinaten | `departureCity.lat`, `departureCity.lng` | Dezimalgrad als Zahlen, im Beispiel sieben Nachkommastellen. |
| Zielkoordinaten | `deliveryCity.lat`, `deliveryCity.lng` | Dezimalgrad als Zahlen, im Beispiel sieben Nachkommastellen. |
| Verfuegbarkeit | `status` | `READY` kennzeichnet im verifizierten Resultat buchbare Angebote. |
| Verfuegbarkeitsfenster | `available_from_date`, `available_to_date` | ISO-8601-Kalenderdatum (`YYYY-MM-DD`). |
| Abfahrtsfenster | `earliest_departure_date`, `latest_departure_date` | ISO-8601-Kalenderdatum (`YYYY-MM-DD`). |
| Preis | `currency`, `hire_unit_rate`, `hire_unit_type`, `booking_fee_amount` | Betragseinheiten sind offenbar Minor Units: `hire_unit_rate: 100` entspricht der auf der Seite beworbenen Rate von EUR 1 pro `NIGHT` bzw. `DAY`; `booking_fee_amount: 9900` entspricht EUR 99. |
| Inklusivdistanz | `distance_allowed` | Ganzzahl; bei `measurement: "METRIC"` Kilometer. |

`available_from_date` und `available_to_date` sind nicht gleichbedeutend mit
dem tatsaechlichen Abfahrtsfenster. Fuer die Terminvalidierung sind
`earliest_departure_date` und `latest_departure_date` die spezifischeren Felder.

## Abweichungen von der Planannahme

1. Der Endpunkt liefert HTML mit serialisierten Client-Cache-Daten statt einer
   direkt parsebaren JSON-Antwort. T09 muss daher den extrahierten
   `RelocationPaginator`-Datensatz als Eingabe erhalten oder die
   HTML-Serialisierung explizit verarbeiten; ein JSON-Parser auf
   `response.json()` ist nicht moeglich.
2. Der Parameter `earliest_departure=2026-07-27` wird in der eingebetteten
   Abfrage als Filter `LATEST_DEPARTURE_DATE >= "2026-07-27"` abgebildet. Die
   Antwort enthielt dennoch Angebote mit `earliest_departure_date` vor dem
   Parameterdatum (zum Beispiel `2026-07-23`). Der Parameter beschraenkt also
   das spaeteste Abfahrtsdatum, nicht zwingend den fruehesten Abfahrtstermin.
3. Die Ergebnismenge ist paginiert. Im verifizierten Aufruf waren `perPage: 18`,
   `count: 18`, `total: 19`, `currentPage: 1`, `lastPage: 2` und
   `hasMorePages: true` gesetzt. Ein Client, der alle Angebote benoetigt, muss
   die weiteren Seiten abfragen.
