# NED Energieweerbericht 0.2.0

[English documentation](README.en.md)

Home Assistant-integratie voor landelijke en provinciale energiedata van het Nationaal Energie Dashboard (NED). Vereist Home Assistant **2026.11.0 of nieuwer** en een NED API-sleutel. De integratie werkt zelfstandig. De landelijke zonneprognose beschrijft landelijke opwek en kan niet worden gebruikt als opbrengstvoorspelling voor je eigen panelen.

## Installatie en configuratie

1. Maak een account aan bij NED. Open **Mijn account → API** en maak daar een sleutel aan.
2. Kies een installatiemethode:
   - **Handmatig** — kopieer de volledige map `custom_components/ned_energy_weather` naar `/config/custom_components/`. Herstart Home Assistant.
   - **Marketplace** — na publicatie ga je naar **Instellingen → Marketplace → Toevoegen via link**. Koppel GitHub wanneer gevraagd, voer de openbare repository-URL in en installeer deze als integratie. Herstart indien gevraagd.
   - **HACS** — open **HACS → menu → Aangepaste repositories**, voeg de URL toe als **Integratie**, download het pakket en herstart Home Assistant.
3. Ga naar **Instellingen → Apparaten en diensten → Integratie toevoegen** en zoek **NED Energieweerbericht**. Voer de sleutel in, kies één provincie en selecteer 15, 30, 60, 120 of 360 minuten. Standaardwaarden zijn Utrecht en 60 minuten. Nederland blijft altijd beschikbaar.
4. Wijzig provincie en interval via **Configureren**. Gebruik **Opnieuw configureren** in het menu van de integratie om de sleutel te vervangen. Bij een verlopen of ingetrokken sleutel verschijnt een herauthenticatieverzoek.

## Catalogus en sensoren

De catalogus bevat 39 combinaties van type en activiteit. Dit omvat elektriciteitsproductie (zon, wind op land en zee, gas, kolen, kernenergie, biomassa, afval, WKK, overige en totaal), elektriciteitsverbruik, warmte en overige duurzame energie (biogas, biomethaan, warmtepompen, geothermie, thermische zon en overige), gasverbruik, elektriciteitsimport en -export, gasstromen en gasopslag.

Voor sensoren en kaart zijn Nederland en de gekozen provincie beschikbaar. Alleen zon (type 2) en wind op land (type 1) hebben provinciale data in de catalogus. Gasimport, gasexport, injectie en opname zijn alleen voor hun eigen NED-meetpunten beschikbaar. Vraag die reeksen op via de actie met het numerieke Point-ID. Landelijke gasopslag is type 28, activiteit 7. Activiteiten 1–7 zijn respectievelijk productie, consumptie, import, export, injectie, opname en opslag. Raadpleeg de catalogus voor alle ID's en de horizons per activiteit.

Elk catalogusrecord in het ingestelde gebied levert een apparaatgroep met uurwaarden. Capaciteit (gemiddeld vermogen, kW) is standaard ingeschakeld. Activeer intervalvolume (kWh), benuttingsgraad (%), CO₂-uitstoot (kg) en emissiefactor (kg/kWh) via de entiteitenlijst. Emissievelden worden alleen aangeboden waar de catalogus CO₂-gegevens vermeldt. NED kan afzonderlijke velden weglaten. Volume is een hoeveelheid per interval en heeft geen optellende state class. Gebruik de normale Home Assistant-geschiedenisgrafiek voor opgenomen sensorstanden. Recorder bouwt die geschiedenis op vanaf installatie.

## Tijdreeksacties

`ned_energy_weather.get_series` heeft een verplichte respons. Geef `type_id` en `activity` op, plus ISO 8601-tijden met offset voor `start` (inclusief) en `end` (exclusief). `area` is `netherlands`, `province` of een toegestaan Point-ID. `granularity` accepteert `15min`, `hour` of `day`. `classification` accepteert `actual`, `forecast` of `historical_forecast` (lokale uurmomentopnamen). De respons bevat `metadata`, `units`, `records` en `availability` (`available`, `empty`, `unsupported`, `stale`). Records bevatten UTC-tijden en meetvelden, met `null` bij ontbrekende waarden. Lokale voorspellingen bevatten ook `issued_at`. De beheerderactie `ned_energy_weather.refresh` haalt actuele uurwaarden opnieuw op.

Deze voorbeelden lezen een respons uit in de uitvoeringstrace. De voorbeelden worden niet automatisch geïnstalleerd.

```yaml
alias: NED - Read provincial solar history
triggers:
  - trigger: time
    at: "08:10:00"
actions:
  - action: ned_energy_weather.get_series
    data:
      area: province
      type_id: 2
      activity: 1
      classification: actual
      granularity: hour
      start: "{{ (utcnow() - timedelta(hours=24)).isoformat() }}"
      end: "{{ utcnow().isoformat() }}"
    response_variable: ned_solar
  - variables:
      sample_count: "{{ ned_solar.records | count }}"
mode: single
```

```yaml
alias: NED - Read national wind forecast
triggers:
  - trigger: time
    at: "13:10:00"
actions:
  - action: ned_energy_weather.get_series
    data:
      area: netherlands
      type_id: 1
      activity: 1
      classification: forecast
      granularity: 15min
      start: "{{ utcnow().isoformat() }}"
      end: "{{ (utcnow() + timedelta(hours=24)).isoformat() }}"
    response_variable: ned_wind
  - variables:
      sample_count: "{{ ned_wind.records | count }}"
mode: single
```

## Lovelace-kaart

Zet Geavanceerde modus aan in je profiel als de resourcepagina ontbreekt. Open **Instellingen → Dashboards → Resources** en voeg `/api/ned_energy_weather/ned-energy-weather-card.js` toe als **JavaScript-module**. Voeg vervolgens een handmatige kaart toe.

```yaml
type: custom:ned-energy-weather-card
title: NED Energieweerbericht
area: netherlands
granularity: hour
datasets: ["2:1", "1:1", "51:1"]
```

Kies een gebied, maximaal vier reeksen, één meetveld, de resolutie en een historisch en toekomstig venster. Klik op **Ophalen**. De grafiek toont actuele waarden, toekomstige voorspellingen en bij uurresolutie beschikbare eerdere voorspellingen. De kaart gebruikt de tijdzone van Home Assistant. De verbinding met NED loopt via de backend.

## Tijdzones, opslag en limieten

- NED staat 200 HTTP-verzoeken per vijf minuten toe. De client telt pagina's en retries mee, gebruikt maximaal drie gelijktijdige verzoeken en respecteert `Retry-After`. Het NED-account kan ook vanuit andere toepassingen worden gebruikt.
- Sensoren halen recente uurdata op. De actie leest tot 30 dagen terug in datumblokken en gebruikt een begrensde cache. Bij een tijdelijke storing kan de actie verlopen cachedata als `stale` teruggeven. Sensoren uit mislukte groepen worden onbeschikbaar terwijl hun laatst ontvangen record bewaard blijft.
- Prognoses lopen maximaal één of zeven dagen vooruit volgens het catalogusrecord. Per Amsterdamse dag bewaart Home Assistant per geconfigureerde reeks de eerste geslaagde uurmomentopname. Vergelijkingen kiezen per doelinterval de nieuwste lokale momentopname van vóór dat interval. Er is geen terugvulling van voor installatie en er zijn geen langjarige referentiewaarden in deze integratie. Opslag bewaart maximaal 30 kalenderdagen en circa 8 MB per installatie. Bij het bereiken van de limiet vervalt eerst de oudste dag.
- De huidige endpoint is `https://api.ned.nl/v1/utilizations`. De oude `api.netanders.io` is vervallen. De tabel geeft UTC als tijdzone-ID 0 en Amsterdam als 1. Het oudere voorbeeld verwisselt het UTC-label bij ID 1. Dagaggregaten vereisen 1, ook bij een dag van 23 of 25 uur. De client presenteert de benuttingsgraad als procent door de fractie uit het JSON-LD-record met 100 te vermenigvuldigen.
- De OpenAPI-specificatie bevestigt de collectieparameters `point[]` en `type[]`, Hydra-paginering en maximaal 200 records per pagina. De veldbeschrijvingen lopen deels achter op de catalogus. Zo missen ze kwartierwaarden en nieuwere activiteiten. De OpenAPI-tekst noemt ton bij `emission`, terwijl de handleiding en API-uitleg kg aangeven. De integratie volgt kg volgens de handleiding. De emissie-eenheid en procentconversie moeten nog tegen een productieantwoord worden gecontroleerd. De tests gebruiken gesimuleerde JSON-LD-responses.

## Problemen oplossen en beheer

- **Ongeldige sleutel** — maak een nieuwe sleutel aan bij NED en kies **Opnieuw configureren**.
- **429 of trage opvraging** — probeer later opnieuw en verklein het tijdvenster. Controleer ander gebruik van dezelfde NED-sleutel.
- **Lege reeks** — controleer Point-ID, activiteit, resolutie en classificatie. NED kan gegevens met vertraging leveren. Een lokale prognosevergelijking verschijnt nadat een momentopname beschikbaar is.
- **Kaart ontbreekt** — controleer het resourcepad en het moduletype, herlaad de browser en controleer of de integratie is geladen.
- **Diagnose** — de diagnostische sensor meldt het laatste succesvolle update-tijdstip en API-beschikbaarheid. Download integratiediagnostiek via het menu voor gegevensversheid en opslagstatus. Diagnostiek bevat geen sleutel. Filter de systeemlog op `custom_components.ned_energy_weather`.
- **Bijwerken** — installeer de nieuwe versie via je pakketbeheerder of vervang de integratiemap en herstart. **Verwijderen** — verwijder eerst de integratie-invoer en de Lovelace-resource. Verwijder daarna het pakket en herstart indien gevraagd. Bij het verwijderen van de invoer wist Home Assistant de lokale prognoseopslag van die invoer.

## Historische day-aheadprijzen

Kies **Day-aheadprijs** bij **Gegevens** op de Lovelace-kaart, selecteer **Vanaf** en **Tot en met** en klik op **Ophalen**. Je kunt per keer maximaal 31 dagen opvragen vanaf 1 januari 2023. De datums volgen de Nederlandse markt (Europe/Amsterdam). De grafiek gebruikt de tijdzone van Home Assistant en toont groothandelsprijzen in €/MWh. Voeg `mode: prices` toe aan de kaartconfiguratie om direct in de prijsweergave te openen.

De prijzen komen van de openbare CSV-download van NED DRP. Die gebruikt een apart eindpunt zonder extra API-sleutel. Voor de energiereeksen blijft je bestaande NED-sleutel nodig. [NED DRP-portaal](https://drp.ned.nl/nl/drp)

```yaml
action: ned_energy_weather.get_prices
data:
  start: "2026-11-09"
  end: "2026-11-09"
response_variable: ned_prices
```

De einddatum is inclusief. Gebruik `ned_prices.records` voor de prijzen. Elk record bevat `valid_from` en `valid_to` in UTC en `day_ahead` in EUR/MWh. Kwartieren waarvoor NED geen day-aheadprijs levert, ontbreken in de reeks.

## Publicatie op GitHub

De projectrepository is [vajpeters/ha-ned-energy-weather](https://github.com/vajpeters/ha-ned-energy-weather). Voor publicatie in een andere lege openbare repository pas je `documentation`, `issue_tracker` en `codeowners` aan in `custom_components/ned_energy_weather/manifest.json`. Voer vanuit de uitgepakte projectmap in Git Bash uit:

```sh
git init -b main
read -r -p "GitHub HTTPS-URL: " REPO_URL
git remote add origin "$REPO_URL"
git add .
git commit -m "Initial NED Energieweerbericht release"
git push -u origin main
git tag v0.2.0
git push origin v0.2.0
```

Maak daarna in GitHub **Releases → Draft a new release** een release voor tag `v0.2.0`. Laat de ingebouwde kaart binnen de integratiemap. Voor opname in de standaard HACS-catalogus gelden aanvullende eisen, waaronder Home Assistant Brands. Een openbare custom repository kan afzonderlijk worden toegevoegd.

## Teststatus en aanvullende NED-data

Versie 0.2.0 is lokaal getest met 19 geautomatiseerde Home Assistant-tests en een Chrome-test met gesimuleerde kaartdata. De prijsclient is live getest zonder sleutel, onder meer met 100 kwartieren op de dag waarop de wintertijd inging. Een live test van de energiereeksen met een geldige NED API-sleutel staat nog open. [GitHub Actions](https://github.com/vajpeters/ha-ned-energy-weather/actions)

- **Historische opwek.** Op 11 november 2026 is de openbare NED-grafiekdata voor landelijke zonne-opwek opgehaald. De reeks bevatte volledige jaarwaarden voor 2018–2025 en een lopende waarde voor 2026. Dezelfde historische proef via de officiële `/v1/utilizations`-API gaf zonder sleutel HTTP 401. NED heeft voor sommige energiedragers historie vanaf januari 2016. De tijdreeksactie van deze integratie kijkt maximaal 30 dagen terug. [Zonne-energie](https://ned.nl/nl/dataportaal/energie-productie/elektriciteit/zonne-energie) · [NED API](https://ned.nl/nl/api)
- **Elektriciteitsprijzen.** Een openbare CSV-download voor 9 november 2026 bevatte 96 kwartieren. Versie 0.2.0 ondersteunt de day-aheadprijs uit die download. Het DRP-portaal publiceert ook de dynamische referentieprijs en onbalansprijzen. [DRP en elektriciteitsprijzen](https://drp.ned.nl/nl/drp)

## Eerste praktijktest

- Installeer de integratie en doorloop de flow met een geldige eigen NED-sleutel.
- Vergelijk zon en wind voor Nederland en Utrecht met de NED API-viewer voor dezelfde UTC-uren.
- Vraag een uurreeks en een dagreeks op. Controleer de respons, eenheden en Amsterdamse daggrenzen.
- Laad de kaart met zon en wind, wijzig het venster en controleer de toekomstige lijn.
- Wijzig provincie en interval. Herstart na een geslaagde snapshot en controleer `historical_forecast` wanneer een voorspeld uur is verstreken.

## Bronnen

- [NED API](https://ned.nl/nl/api) · [Handleiding](https://ned.nl/nl/handleiding-api) · [Datacatalogus](https://ned.nl/nl/datacatalogus) · [OpenAPI-specificatie](https://api.ned.nl/v1/docs.jsonopenapi)
- [Home Assistant Contributors](https://contributors.home-assistant.io/) · [Marketplace](https://www.home-assistant.io/integrations/marketplace/#custom-repositories) · [HACS integration requirements](https://hacs.dev/docs/publish/integration/)
