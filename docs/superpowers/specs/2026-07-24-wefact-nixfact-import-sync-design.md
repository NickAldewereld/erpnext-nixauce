# WeFact → NIXFact import + sync — ontwerp

**Datum:** 2026-07-24
**Status:** vastgesteld, klaar voor implementatieplan
**Repo:** `/mnt/nvme1tb/projects/erpnext-nixauce`, app `nixfact_integration`
**Bouwt voort op:** Fase 1 NIXFact Kantoor (factuurregels, UBL, validatiehook) — branch `fase-1-factuurregels`

## 1. Doel

Eén replicatie-engine die de volledige WeFact-administratie naar NIXFact spiegelt, in twee draaimodi met dezelfde mapping-kern:

- **Volledige backfill** — eenmalig alle historische gegevens importeren.
- **Incrementele sync** — daarna periodiek (`modified_since`) bijwerken.

De richting is **eenrichting: WeFact → NIXFact**. WeFact blijft (voorlopig) het primaire systeem; NIXFact draait in **schaduwmodus** en spiegelt mee zonder naar buiten te handelen, totdat Nick op basis van performance geleidelijk cutovert.

**Succes:** na de backfill staan 276 debiteuren, 815 verkoopfacturen (met regels), 335 inkoopfacturen (met regels én PDF-bijlagen) en 29 abonnementen in NIXFact onder company Aldewereld Consultancy; herdraaien maakt geen dubbels; de incrementele run houdt het spiegelbeeld actueel; en NIXFact stuurt in de schaduwfase niets naar echte klanten.

## 2. Scope

**In scope:**
- Debiteuren → ERPNext Customer + Address
- Verkoopfacturen → NixFact Factuur + NixFact Factuur Regel (incl. creditnota's)
- Inkoopfacturen → NixFact Inkoopfactuur + regels + **PDF-bijlagen**
- Abonnementen → NixFact Abonnement (facturering uit — zie §6.1)
- Incrementele sync-engine + cursor

**Buiten scope (bewust, YAGNI):**
- De 51 WeFact-producten als eigen entiteit — er is geen NIXFact-productdoctype; prijs en omschrijving staan al op de factuur- en abonnementsregels.
- Terugschrijven naar WeFact (de sync is eenrichting).
- Offertes uit WeFact (niet gevraagd; NIXFact heeft een eigen offerteflow).

## 3. Uitgangssituatie (uit recon 2026-07-24)

WeFact v2 API (`https://api.mijnwefact.nl/v2/`), volumes:

| Entiteit | Aantal | Detail-fetch nodig voor regels? |
|---|---|---|
| Debiteuren | 276 | nee (lijst bevat alles) |
| Verkoopfacturen | 815 | **ja** — `InvoiceLines` alleen in `invoice/show` |
| Inkoopfacturen | 335 | **ja** — `InvoiceLines` + `Attachments` in detail |
| Abonnementen | 29 | nee |
| Producten | 51 | n.v.t. (buiten scope) |

Circa **1.150 detail-fetches** voor volledige regel-getrouwheid — dit is de bottleneck van de backfill (WeFact-rate, niet NIXFact).

**Recon-bevindingen die het ontwerp sturen:**
- WeFact-statuscodes wijken af van hun eigen documentatie: `8`/`9` zijn creditnota / gecrediteerd origineel. `Translations.Status` (de tekst) is de betrouwbare bron, niet het nummer.
- Debiteur-`Modified` is bij ~40% leeg → incrementele sync mag leeg niet als "oud, overslaan" lezen.
- Company/persoon wordt afgeleid uit lege `CompanyName` (dan is het een privépersoon met `Initials`/`SurName`).
- Inkoopfactuurregels gebruiken tax-codes met `I`-prefix (`I21`) i.p.v. `V`-prefix voor verkoop, plus een `CostCategory`-veld (boekhoudcategorie, los van BTW).
- WeFact-bedragen/tarieven staan per regel (`PriceExcl`, `TaxPercentage`, `Number` als aantal, `NumberSuffix` als eenheid).

## 4. Architectuur

Een Python-subpakket in de bestaande Frappe-app: `nixfact_integration/nixfact_integration/wefact_sync/`. WeFact wordt via REST uitgelezen; NIXFact-documenten worden **direct via de Frappe-ORM** aangemaakt (geen REST-heen-en-weer), zodat Fase 1 (regelberekening, doctypes) hergebruikt wordt.

### 4.1 Lagen

- **`client.py`** — dunne WeFact-REST-client (auth, paginatie, `modified_since`, rate-limit-backoff). Enige plek die HTTP doet.
- **`mapping/`** — pure functies `wefact_debtor → customer_dict`, `wefact_invoice → factuur_dict`, enz. **Geen frappe, geen HTTP** → volledig in CI testbaar met fixtures (zoals de Fase 1 pure laag).
- **`upsert.py`** — idempotente ORM-laag: zoek bestaand doc op `wefact_identifier`, maak aan of werk bij. Enige plek die de database raakt.
- **`engine.py`** — orkestratie: per entiteittype ophalen → mappen → upserten, met per-record-isolatie en zichtbare foutrapportage (§9).
- **`cursor.py`** — leest/schrijft de laatste succesvolle sync-tijd per entiteit in NixFact Instellingen.

### 4.2 Entry-points

- **Backfill:** `bench --site … execute nixfact_integration.wefact_sync.engine.volledige_backfill` (optioneel per entiteit: `--kwargs '{"alleen": "facturen"}'`).
- **Incrementeel:** Frappe-scheduler, uurlijks: `nixfact_integration.wefact_sync.engine.incrementele_sync`. Toegevoegd aan `scheduler_events` in `hooks.py`, naast de bestaande jobs.

## 5. Mapping

### 5.1 Debiteur → Customer + Address

- Customer: `customer_name` = `CompanyName` of (bij leeg) `Initials + SurName`; `customer_type` = "Company"/"Individual" naar gelang `CompanyName`; `tax_id` = `TaxNumber`; `wefact_identifier` = `Identifier`; `wefact_debtor_code` = `DebtorCode` (voor koppeling van facturen).
- Address: één primair adres uit `Address`/`ZipCode`/`City`/`Country`; gekoppeld aan de Customer. Nodig voor Fase 1-UBL (land is verplicht).
- Meerdere e-mailadressen in `EmailAddress` (gescheiden door `;`) → eerste als primair, rest in een opmerking.

### 5.2 Verkoopfactuur → NixFact Factuur + regels

- Kop: `klant` via `wefact_debtor_code` → Customer; `company` = Aldewereld Consultancy (§7); `factuur_datum` = `Date`; `factuurnummer` = `InvoiceCode`; `referentie` = `ReferenceNumber`; `wefact_identifier` = `Identifier`.
- Regels uit `InvoiceLines`: `omschrijving` = `Description`; `aantal` = `Number`; `eenheidsprijs` = `PriceExcl`; `btw_percentage` = `TaxPercentage`; `btw_categorie` afgeleid uit `TaxPercentage` (0 → Nultarief, >0 → Standaard; `Verlegd`/`Vrijgesteld` alleen als de tax-code dat aangeeft).
- **Status:** gemapt uit `Translations.Status` (tekst), niet uit het nummer. Mapping-tabel in `mapping/status.py`, met een expliciete `onbekend → Concept + waarschuwing`-fallback zodat een nieuwe WeFact-status nooit stil verkeerd landt.
- **Creditnota's** (negatief bedrag / status-tekst "credit", WeFact-status 8/9): herkend en gemarkeerd. Doelmodel — default: een NixFact Factuur met negatieve regelbedragen plus een markering, gekoppeld aan het originele factuurdoc via `wefact_identifier`. (Fase 1 staat negatieve regelbedragen al toe.) Of NIXFact een apart creditnota-mechanisme heeft wordt in fase 3 geverifieerd; zo niet, dan geldt de default.
- **Nummerbotsing vermijden:** de import zet `factuurnummer` letterlijk op de WeFact-code en slaat NIXFacts eigen nummergenerator over (die is voor nieuw uitgaand werk ná cutover).

### 5.3 Inkoopfactuur → NixFact Inkoopfactuur + regels + PDF

- Crediteuren → ERPNext Supplier (analoog aan debiteur→Customer), met `wefact_identifier` = crediteur-`Identifier` en `wefact_creditor_code` voor koppeling. Aangemaakt vóór de eerste inkoopfactuur die ernaar verwijst.
- Kop uit `credit_invoice/show`: leverancier via `CreditorCode` → Supplier; `InvoiceCode` (leverancier-nummer) → referentie; `wefact_identifier` = `Identifier`; bedragen/status.
- Regels uit `InvoiceLines` (`I`-prefix tax-codes; `CostCategory` → NixFact Kostencategorie indien aanwezig, anders leeg).
- **PDF-bijlagen:** elk item in `Attachments` downloaden en als privé-File aan de Inkoopfactuur hangen (idempotent, zoals Fase 1's `generate_and_attach_ubl`: bestaande bijlage met dezelfde naam eerst verwijderen). Dit is de zwaarste extra I/O van de backfill; per-record-geïsoleerd zodat één corrupte bijlage de rest niet stopt.

### 5.4 Abonnement → NixFact Abonnement

- Velden uit `subscription/show`: klant, omschrijving, bedrag, `btw_percentage`; `frequentie` uit `Periodic` (`m`→Maandelijks, `k`→Kwartaal, `j`→Jaarlijks, gecombineerd met `Periods`); `volgende_factuur_datum` = `NextDate`; `wefact_identifier` = `Identifier`.
- **Facturering staat uit** (§6.1). `volgende_factuur_datum` = WeFacts `NextDate` zodat facturering ná cutover naadloos verdergaat op de juiste datum.

## 6. Safeguards (de kern van dit ontwerp)

Vier interacties die stil fout gaan zonder expliciete regel. Drie ervan raken Fase 1-gedrag.

### 6.1 Geen dubbele facturering

WeFact genereert de 29 abonnementsfacturen; Fase 1 heeft een eigen abonnement-cron. Geïmporteerde abonnementen komen binnen met facturering **uit**, en de globale `auto_factureren_abonnementen` blijft **uit** tot cutover. Zonder deze regel maken WeFact én NIXFact dezelfde factuur, en de sync haalt WeFacts versie er bovenop binnen.

### 6.2 Import omzeilt de Peppol-validatiehook

Fase 1's `before_save`-hook blokkeert status→Verstuurd als de factuur niet EN16931-geldig is. Veel oude WeFact-klanten missen een compleet adres/BTW-nummer → dat zou de import blokkeren. **Regel:** `valideer_factuur_doc` krijgt een vroege `return` zodra het doc een `wefact_identifier` draagt. Historische administratie toets je niet tegen de e-facturatie-eisen van vandaag; die facturen zijn nooit via Peppol verstuurd.

### 6.3 Schaduwmodus-invariant: WeFact-eigendom is inert

Een geïmporteerde onbetaalde factuur staat op "Verstuurd" met oude vervaldatum. Fase 1's dagelijkse `verstuur_herinneringen`/`verstuur_aanmaningen` zouden dan **echte klanten aanmaningen sturen**. Kernregel, breder dan alleen aanmaningen:

> **Elk doc met een niet-lege `wefact_identifier` is WeFact-eigendom. NIXFact voert er nooit een uitgaande actie op uit** — geen herinnering, geen aanmaning, geen Peppol-verzending, geen Mollie-betaallink.

Implementatie: de queries in `tasks.py` (`verstuur_herinneringen`, `verstuur_aanmaningen`) krijgen een filter `wefact_identifier is leeg`. Dit maakt schaduwdraaien veilig by design en overleeft de cutover: zodra Nick een factuur in NIXFact zélf maakt (zonder `wefact_identifier`) pakt de normale flow die wél op.

### 6.4 Statustekst boven statusnummer

Alle statusafleiding gaat via `Translations.Status`. Onbekende status → veilige default (Concept) + waarschuwing in het runrapport, nooit stil een verkeerde status.

## 7. Company

Doelcompany voor alle verkoopfacturen en debiteuren: **Aldewereld Consultancy** (KvK 61862533, BTW NL002168402B79). Bestaat die company nog niet in de ERP, dan maakt de backfill hem aan vóór de eerste factuur. Nixpay B.V. blijft een losse company. Inkoopfacturen: company gelijk aan de verkoopkant tenzij een WeFact-veld anders aangeeft (default Aldewereld Consultancy).

## 8. Idempotentie

Elk geïmporteerd doctype krijgt een indexeerbaar `wefact_identifier`-veld (Data). Customer krijgt daarnaast `wefact_debtor_code` (voor factuurkoppeling). De upsert-laag zoekt eerst op `wefact_identifier`; gevonden → bijwerken, niet gevonden → aanmaken. Herdraaien van backfill of sync is daardoor volledig idempotent. De velden worden als custom fields toegevoegd aan Customer (ERPNext-standaard) en als gewone velden aan de NixFact-doctypes.

## 9. Foutafhandeling

Per record geïsoleerd (zoals de Fase 1 abonnement-cron): elk record in zijn eigen try/except; een fout rolt alleen dat record terug, logt de reden, en de run gaat door. Aan het eind een **zichtbaar rapport**: `X verwerkt, Y mislukt, uit Z`, met per mislukking entiteit + WeFact-code + reden (HTML-vrij), zowel als scheduler-logregel als geconsolideerde Error Log — hetzelfde patroon dat Fase 1 voor de abonnement-cron kreeg. Geen stille mislukking.

WeFact-rate-limiting: de client doet exponentiële backoff op HTTP 429 en hervat; de backfill is herstartbaar omdat hij idempotent is (opnieuw draaien slaat reeds-geïmporteerde over op `Modified`-vergelijking).

## 10. Draaimodi en cursor

- **Backfill:** negeert de cursor, loopt alle entiteiten volledig af (debiteuren → producten n.v.t. → verkoopfacturen → inkoopfacturen → abonnementen; debiteuren eerst zodat facturen kunnen koppelen). Schrijft aan het eind per entiteit de cursor op `max(Modified)`.
- **Incrementeel:** leest de cursor per entiteit, roept elke WeFact-lijst met `modified_since` aan, verwerkt alleen gewijzigde records. **Debiteuren:** vanwege lege `Modified` draait de debiteur-sync óók een goedkope volledige lijstscan (alleen kop, geen detail) en vergelijkt inhoud, zodat klanten met lege `Modified` niet gemist worden.
- Cursor per entiteit in NixFact Instellingen (`wefact_cursor_facturen`, `_debiteuren`, enz.).

## 11. Configuratie

- WeFact API-key: veld in NixFact Instellingen (of env op R220, consistent met de bestaande secrets in `/root/nixfact-bridge.env`).
- `wefact_sync_enabled` (bool) — killswitch voor de scheduler.
- De cursorvelden uit §10.

## 12. Testen

- **Pure mapping-tests (CI):** fixtures = echte (geanonimiseerde) WeFact-JSON-payloads uit de recon; assert dat `wefact_invoice → factuur_dict` de juiste regels, btw-categorieën, statusmapping en creditnota-detectie oplevert. Zelfde stijl als de Fase 1 pure laag.
- **Statusmapping-tests:** elke bekende `Translations.Status` → juiste NIXFact-status; onbekend → Concept + waarschuwing.
- **Idempotentie-test:** tweemaal dezelfde payload upserten levert één doc.
- **Safeguard-tests:** een doc met `wefact_identifier` wordt overgeslagen door de herinnering/aanmaning-queries en door de validatiehook (unit, met gestubde frappe waar mogelijk).
- **Integratie (bench, handmatig):** kleine `limit_pages=1`-backfill tegen de echte WeFact-API op een schone bench; controleer aantallen en een steekproef.

## 13. Fasering voor het plan

1. **Schema + idempotentie:** `wefact_identifier`/`wefact_debtor_code`-velden, cursor-velden, config. Migratie-veilig.
2. **Client + pure mapping + tests:** WeFact-client en de frappe-vrije mapping-laag met fixture-tests. Geen DB.
3. **Upsert + engine (debiteuren + facturen):** de kern-entiteiten end-to-end, backfill-entrypoint, zichtbaar rapport.
4. **Inkoopfacturen + PDF-bijlagen.**
5. **Abonnementen (billing uit) + de vier safeguards** (incl. de Fase 1 hook/tasks-aanpassingen).
6. **Incrementele sync + scheduler + cursor.**

Elke fase levert werkende, testbare software op.

## 14. Afhankelijkheid van Fase 1

Deze engine bouwt op Fase 1 (factuurregels, validatiehook) en past twee Fase 1-bestanden aan (`ubl_generator.py` hook-bypass, `tasks.py` reminder/dunning-filter). Het werk hoort dus **boven op** `fase-1-factuurregels` te stacken, of te starten nadat Fase 1 gemerged en bench-geverifieerd is.
