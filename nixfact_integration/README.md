# NixFact Integration

A WeFact-inspired invoicing and billing system built as a custom
[Frappe](https://frappeframework.com/) application on top of ERPNext.

## Overview

`nixfact_integration` adds Dutch-market invoicing workflows to ERPNext:

- **Offertes** (quotations) with a customer portal and digital signing
  (canvas signature + IP/email/user-agent audit trail).
- **Facturen** (invoices) and **Abonnementen** (recurring/subscription billing).
- **Inkoopfacturen** (purchase invoices) and **Kostencategorieën** (cost
  categories).
- **Bank integration** (Ponto) via Bank Koppeling / Bank Transactie doctypes.
- **Mollie** online payments.
- **UBL 2.1** e-invoicing.
- A central **NixFact Instellingen** singleton for configuration.

## Requirements

- Frappe `>=17.0.0-dev,<18.0.0` (the v17 dev line)
- Python `>=3.14` and Node `>=24` (as required by Frappe's develop branch)
- ERPNext (same branch as Frappe)

## Installation

```bash
bench get-app https://github.com/NickAldewereld/erpnext-nixauce
bench --site <site> install-app nixfact_integration
```

For a containerised production deployment, see `deployment/docker/` and the
design/plan documents under `docs/superpowers/`.

## License

AGPL-3.0-or-later. A separate commercial license is available — contact
nick@nixpay.nl.
