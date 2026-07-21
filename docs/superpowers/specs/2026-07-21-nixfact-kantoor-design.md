# NIXFact Kantoor — ontwerp

**Datum:** 2026-07-21
**Status:** vastgesteld, klaar voor implementatieplan
**Repo:** `/mnt/nvme1tb/projects/erpnext-nixauce`

## 1. Doel

Eén herhaalbaar abonnementsproduct maken van de bestaande NIXFact-codebase: e-facturatie (Peppol) plus automatisch afletteren, verkocht **per administratiekantoor**.

Het kantoor is de klant, niet het MKB-bedrijf. Eén kantoor brengt 50-200 MKB-klanten mee. Dat is de hefboom die van uren-voor-geld naar terugkerende omzet leidt.

**Wat succes betekent op maand 6:** drie pilotkantoren draaien productie, minstens één betaalt, en een nieuw kantoor aansluiten kost minder dan een kwartier handwerk. Niet: een omzetbedrag. €10-30k MRR ligt op maand 12-18 bij ongeveer vijf kantoren met elk 60-100 klanten.

## 2. Waarom een kantoor hiervoor betaalt

Niet om Peppol. Peppol is een verplichting die ze moeten afvinken, en tien leveranciers vinken hem af.

Ze betalen voor **één scherm over al hun klanten heen**: wie moet nog factureren, wat is niet afgeletterd, welke verzendingen zijn gefaald. Vandaag is dat werk twintig keer inloggen en handmatig vergelijken. De cockpit is het product; het Peppol- en bankwerk eronder is de plumbing die de cockpit voedt.

Het onderscheidende deel van de codebase is dan ook niet de UBL-generator (die bouwt iedereen) maar de bestaande Ponto-koppeling met de driestaps-matcher die op ≥95% zekerheid automatisch afletteren — plus Mollie voor betaallinks. Die combinatie is duur om na te bouwen.

## 3. Uitgangssituatie (feitelijk, per 2026-07-21)

Aanwezig:

- Frappe-app `nixfact_integration` met 8 doctypes, 70 commits, draaiend in LXC 218 op de R220 (`erp.aldewereldconsultancy.nl`).
- `utils/ubl_generator.py` — geldige Peppol BIS 3.0 UBL 2.1 XML met lxml.
- `integrations/mollie.py` — betaallinks plus webhook-afhandeling.
- `integrations/ponto.py` + `utils/bank_matching.py` — bankkoppeling met driestaps-matching en auto-afletteren.
- Offerte-portal met handtekening, abonnementsmodule, aanmaningen via scheduler.
- Docker-compose deployment met systemd-units, age-encrypted backups.

Ontbrekend of blokkerend:

- **`NixFact Factuur` heeft geen regel-items.** Eén bedrag, één BTW-percentage. Daardoor produceert de UBL-generator één regel voor het hele factuurbedrag en is `TaxCategory` hardcoded `S`. Onverkoopbaar buiten eigen gebruik.
- Geen verzending: geen access point, geen AS4, geen SMP-lookup, geen inkomende facturen.
- Geen EN16931-validatie.
- `doc_events` in `hooks.py` staat uitgecommentarieerd; UBL-aanmaak is alleen handmatig via API.
- Eén site, één database. Geen provisioning voor extra klanten.

## 4. Architectuurkeuzes

### 4.1 Peppol-transport: gehuurd nu, eigen later

Verzenden gaat via een gecertificeerd Nederlands access point (Storecove) achter een eigen interface. Parallel, buiten deze spec, loopt het traject om zelf gecertificeerd Access Point te worden.

Overwogen alternatieven: direct zelf certificeren (3-6 maanden, blokkeert alle omzet) of permanent huren (geen moat, marge lekt weg per document). De gekozen route levert binnen weken omzet en houdt de deur open, tegen de prijs van één adapter die twee keer geschreven wordt — enkele dagen werk.

De interface `PeppolTransport` isoleert de leverancier volledig:

```
send(ubl_xml: str, receiver_id: str) -> VerzendResultaat
lookup(identifier: str) -> OntvangerInfo | None      # SMP-lookup
ontvang(payload: dict) -> InkomendDocument           # inbound webhook
```

Geen enkele aanroepende code kent Storecove. Omzetten naar het eigen AP is één nieuwe implementatie plus een configuratieveld.

### 4.2 Tenancy: één site per kantoor

Eén Frappe-site per administratiekantoor, daarbinnen ERPNext multi-company met één company per MKB-klant.

Overwogen alternatieven: één site per MKB-klant (200 databases per kantoor, onbeheersbaar) of alles op één gedeelde site (kantoren zien elkaars data — onacceptabel, en juridisch problematisch bij een verwerkersovereenkomst). De gekozen tussenweg geeft harde isolatie op de grens die er juridisch toe doet, en vijf kantoren passen ruim in vijf containers op de R220.

Frappe ondersteunt multi-site native in één bench; dit is een deploy-vraagstuk, geen herbouw.

### 4.3 Volgorde

Regel-items gaan vóór al het Peppol-werk. Zonder regel-items is elke UBL één regel en is elke verdere investering in verzending weggegooid.

## 5. Onderdelen

Elk onderdeel is los te begrijpen, los te testen, en heeft één duidelijke verantwoordelijkheid.

### 5.1 Factuurregels

Nieuw child doctype `NixFact Factuur Regel`: omschrijving, aantal, eenheidsprijs, BTW-percentage, BTW-categorie, regeltotaal. Gekoppeld aan `NixFact Factuur` en `NixFact Inkoopfactuur`.

Migratie: elke bestaande factuur krijgt één regel met het huidige bedrag en BTW-percentage. De bestaande totaalvelden blijven bestaan en worden voortaan berekend uit de regels, zodat rapportages en de offerte-portal blijven werken.

*Afhankelijk van:* niets. *Levert:* een factuurmodel dat een echte factuur kan representeren.

### 5.2 UBL-generator v2

Herschrijven naar meerdere regels, met BTW-categorie per regel: `S` (standaard), `AE` (verlegd), `Z` (nultarief), `E` (vrijgesteld). `TaxTotal` en `TaxSubtotal` worden per categorie gegroepeerd. De uitgecommentarieerde `doc_events`-hook gaat aan, zodat UBL automatisch meekomt bij het versturen van een factuur.

*Afhankelijk van:* 5.1. *Levert:* geldige EN16931-conforme XML voor realistische facturen.

### 5.3 Validatie

EN16931-validatie draait vóór verzending. Een ongeldige factuur wordt geblokkeerd met een Nederlandstalige melding die zegt welk veld ontbreekt — niet een schematron-dump. Dit voorkomt de meest voorkomende supportvraag van een kantoor.

*Afhankelijk van:* 5.2. *Levert:* de garantie dat niets kapots de deur uitgaat.

### 5.4 Transport-adapter

`PeppolTransport` zoals in 4.1, met Storecove-implementatie. Bevat SMP-lookup zodat de gebruiker vóór verzending ziet of een ontvanger bereikbaar is via Peppol, en anders automatisch terugvalt op e-mail met UBL-bijlage.

*Afhankelijk van:* 5.3. *Levert:* daadwerkelijke aflevering bij de ontvanger.

### 5.5 Inkomende e-facturen

Inbound webhook maakt een `NixFact Inkoopfactuur` en biedt die direct aan de bestaande Ponto-matcher aan. Hergebruikt `utils/bank_matching.py` ongewijzigd.

*Afhankelijk van:* 5.4. *Levert:* de tweede helft van "factuur → betaald", en de reden dat een kantoor dit boven een losse verzendtool verkiest.

### 5.6 Provisioning

Script `new-kantoor.sh`: nieuwe Frappe-site in de bestaande bench, subdomein, Caddy-route, seed-configuratie, beheerdersaccount. Idempotent, zoals het bestaande `init.sh`.

*Afhankelijk van:* niets. *Levert:* een nieuw kantoor live in minder dan een kwartier, zonder handwerk.

### 5.7 Kantoor-cockpit

Eén pagina over alle companies binnen de site heen, met drie blokken: te factureren, niet afgeletterd, gefaalde verzendingen. Elke regel klikt door naar het onderliggende document.

*Afhankelijk van:* 5.1 tot en met 5.5. *Levert:* de reden dat het kantoor betaalt.

### 5.8 Eigen abonnementen

Kantoren worden gefactureerd via NIXFacts eigen abonnementsmodule, met Mollie-incasso. Dogfooding en verkoopdemo tegelijk: het kantoor krijgt zijn eigen factuur uit het product dat het koopt.

*Afhankelijk van:* 5.1. *Levert:* de MRR zelf, plus het bewijs dat het werkt.

## 6. Gegevensstroom

Uitgaand: factuur opgeslagen → validatie → UBL gegenereerd → async verzendjob → transport → Peppol-netwerk → ontvanger. Statuswijzigingen komen terug op `NixFact Peppol Verzending`.

Inkomend: webhook → inkoopfactuur → bankmatcher → afgeletterd of open.

Betaling: Mollie-betaallink of banktransactie via Ponto → matcher → factuurstatus → cockpit.

## 7. Foutafhandeling

Verzending is een async job met retry en exponentiële backoff. Elke poging landt in doctype `NixFact Peppol Verzending` met status, foutcode, tijdstempel en payload — een dode brievenbus die niets weggooit.

Het uitgangspunt: **niets faalt stil.** Een mislukte verzending is een rode regel in de cockpit met een leesbare oorzaak. Een kantoor dat er drie weken later achter komt dat facturen nooit zijn aangekomen, is een kantoor dat opzegt en het navertelt.

Validatiefouten blokkeren vóór verzending en zijn dus geen retry-geval maar een gebruikersactie.

## 8. Testen

- Unit: regeltotalen en BTW-groepering per categorie; UBL-uitvoer vergeleken met officiële EN16931-voorbeeldbestanden; migratie van bestaande facturen naar één regel.
- Integratie: verzending en ontvangst tegen de Storecove-testomgeving; retry- en dodebrievenbusgedrag bij een geforceerde fout.
- Smoke: `new-kantoor.sh` draait twee keer achter elkaar op een schone bench en levert een werkende site.

Bestaande CI (ruff plus pure-helper-tests) wordt uitgebreid met de nieuwe unit-tests.

## 9. Buiten scope

Bewust niet in deze spec, omdat ze de eerste betalende klant niet dichterbij brengen: eigen AP-certificering (apart traject), koppeling met het Nixpay-orchestratieplatform, SEPA-incasso, mobiele app, Tolaria-brug, en geautomatiseerde doorbelasting van het kantoor aan zijn eigen MKB-klanten (het kantoor regelt dat zelf; wij factureren alleen het kantoor).

## 10. Commercieel kader

Dit stuurt de scope en hoort daarom in de spec.

Drie pilotkantoren draaien gratis in Q3 2026 in ruil voor gebruik en een referentie. Betalend vanaf Q4. Prijsmodel: vast bedrag per kantoor per maand plus een bedrag per aangesloten MKB-klant per maand — het kantoor rekent door aan zijn klanten en verdient eraan.

Het risico is niet technisch maar commercieel: een kantoor dat al aan een leverancier vastzit, wisselt niet zonder pijn. De pilots moeten daarom uit kantoren komen die nu nog handmatig werken of net moeten kiezen vanwege de e-facturatieverplichting.
