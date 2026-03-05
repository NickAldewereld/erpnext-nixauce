# Configuration Guide

All settings are managed via the **NixFact Instellingen** singleton.

Navigate to: Search "NixFact Instellingen" in the desk.

## Sections

### Algemeen (General)

| Setting | Default | Description |
|---------|---------|-------------|
| Standaard verzendmethode | Email | Default send method for invoices |
| Prijzen inclusief BTW | Yes | Whether prices include VAT |
| Resultaten per pagina | 100 | List view page size |
| Dagelijkse email notificatie | No | Send daily summary email |

### Nummering (Numbering)

| Setting | Default | Description |
|---------|---------|-------------|
| Factuur voorvoegsel | FAC | Invoice number prefix |
| Factuur volgnummer | 1 | Next invoice sequence number |
| Gebruik jaar in factuurnummer | Yes | Include year: FAC-**2026**-001 |
| Gebruik maand in factuurnummer | No | Include month: FAC-2026-**03**-001 |
| Offerte voorvoegsel | OFF | Quote number prefix |
| Offerte volgnummer | 1 | Next quote sequence number |
| Inkoopfactuur voorvoegsel | INK | Purchase invoice prefix |
| Inkoopfactuur volgnummer | 1 | Next purchase invoice sequence |

**Number format examples:**
- Year + month: `FAC-2026-03-001`
- Year only: `FAC-2026-001`
- Simple: `FAC-001`

### Facturatie (Invoicing)

| Setting | Default | Description |
|---------|---------|-------------|
| Betalingstermijn facturen | 14 days | Default payment term |
| UBL e-facturatie | Geen UBL | Options: Geen UBL, Alleen UBL XML, PDF + UBL bijlage |
| PDF bijlagen samenvoegen | No | Merge PDF attachments |

### Herinneringen (Reminders)

| Setting | Default | Description |
|---------|---------|-------------|
| Dagen na vervaldatum voor herinnering | 7 | Days after due date to send reminder |
| Aantal herinneringen | 1 | Number of reminders before summons |
| Dagen na herinnering voor aanmaning | 7 | Days after reminder to send summons |
| Negatief openstaand blokkeren | No | Block negative outstanding amounts |

### Offertes (Quotes)

| Setting | Default | Description |
|---------|---------|-------------|
| Geldigheid offertes | 30 days | Quote validity period |
| Email notificatie bij acceptatie | No | Notify on quote acceptance |
| Automatisch acceptatiebevestiging | No | Auto-send acceptance confirmation |

### Abonnementen (Subscriptions)

| Setting | Default | Description |
|---------|---------|-------------|
| Automatisch factureren | Yes | Auto-generate invoices from subscriptions |
| Dagen vooraf factureren | 1 | Days before billing date to generate |
| Factureren tijdstip | 09:00 | Time of day to run subscription billing |
| Facturen samenvoegen | No | Merge invoices for same customer on same date |

### BTW (VAT)

| Setting | Default | Description |
|---------|---------|-------------|
| Standaard verkoop BTW | 21% | Default sales VAT rate |
| Standaard inkoop BTW | 21% | Default purchase VAT rate |

### Betaalmogelijkheden (Payments)

| Setting | Default | Description |
|---------|---------|-------------|
| Mollie inschakelen | No | Enable Mollie payment integration |
| Mollie API Key | - | Mollie API key (stored encrypted) |
| SEPA incasso inschakelen | No | Enable SEPA direct debit |

### Bank

| Setting | Default | Description |
|---------|---------|-------------|
| Bankkoppeling toestaan | Yes | Allow bank connections |
| Automatisch matchen | Yes | Auto-match transactions to invoices |
| Transacties verwijderen | No | Allow deleting bank transactions |
