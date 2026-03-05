# Architecture

## Overview

NIXFact is a custom Frappe app (`nixfact_integration`) that runs on top of ERPNext. It provides a complete invoicing workflow inspired by WeFact, using ERPNext's Customer/Supplier/Company entities as the base.

## DocTypes

| DocType | Type | Purpose |
|---------|------|---------|
| NixFact Instellingen | Singleton | Global settings for all modules |
| NixFact Offerte | Standard | Quotations with auto-numbering |
| NixFact Factuur | Standard | Sales invoices (auto-numbered, BTW calc, Mollie, UBL) |
| NixFact Abonnement | Standard | Recurring subscriptions |
| NixFact Inkoopfactuur | Standard | Purchase invoices with cost categories |
| NixFact Kostencategorie | Standard | Expense categories for purchase invoices |
| NixFact Bank Koppeling | Standard | Bank connection config (Ponto credentials) |
| NixFact Bank Transactie | Standard | Imported bank transactions with matching |

## Data Flow

### Invoice Lifecycle

```
Create (Concept) → Send (Verstuurd) → Payment
                                        ├── Mollie webhook → Betaald
                                        ├── Bank match (auto) → Betaald
                                        └── Manual → Betaald
                   Overdue?
                   ├── +7 days → Herinnering verstuurd
                   └── +14 days → Aanmaning verstuurd
```

### Subscription Billing

```
NixFact Abonnement (Actief, volgende_factuur_datum = today)
  ↓ tasks.genereer_abonnement_facturen (daily 09:00)
  ↓
NixFact Factuur (created, status = Verstuurd)
  ↓
Abonnement.volgende_factuur_datum += frequentie
```

### Bank Matching

```
Ponto API → NixFact Bank Transactie (Onverwerkt)
  ↓ bank_matching.match_transaction()
  ├── Strategy 1: Invoice number in text → 100% confidence
  ├── Strategy 2: Amount + customer + date → 90-95%
  └── Strategy 3: Fuzzy name → 60-80%
  ↓
  >= 95%: auto_afletteren → Factuur.status = Betaald
  < 95%: status = Match gevonden (manual review)
```

## Auto-Numbering

Configured in NixFact Instellingen. Counter stored in singleton, incremented atomically via `frappe.db.set_single_value()`.

```
DOCTYPE_NUMBERING registry (utils/numbering.py):
  NixFact Offerte    → offerte_voorvoegsel + offerte_volgnummer
  NixFact Factuur    → factuur_voorvoegsel + factuur_volgnummer
  NixFact Inkoopfactuur → inkoopfactuur_voorvoegsel + inkoopfactuur_volgnummer
```

Format: `{prefix}-{year?}-{month?}-{counter:03d}`

## Scheduled Jobs

| Job | Schedule | Function |
|-----|----------|----------|
| Payment reminders | Daily | `tasks.verstuur_herinneringen` |
| Payment summons | Daily | `tasks.verstuur_aanmaningen` |
| Subscription billing | 09:00 daily | `tasks.genereer_abonnement_facturen` |

## External Integrations

### Ponto (Bank)
- OAuth2 refresh token flow
- Transaction sync with deduplication
- `integrations/ponto.py`

### Mollie (Payments)
- Payment creation with metadata
- Webhook for status updates (guest-accessible)
- `integrations/mollie.py`

### UBL 2.1 (E-Invoicing)
- Peppol BIS 3.0 compliant XML generation
- lxml-based builder with proper namespace handling
- Attaches as private file to invoice
- `utils/ubl_generator.py`

## Multi-Company

All invoice/purchase/subscription DocTypes include a `company` field (Link to Company). Numbering supports per-company prefixes. Queries filter by company where applicable.
