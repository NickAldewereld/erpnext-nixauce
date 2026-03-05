# NIXFact

[![CI](https://github.com/NickAldewereld/erpnext-nixauce/actions/workflows/ci.yml/badge.svg)](https://github.com/NickAldewereld/erpnext-nixauce/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Frappe](https://img.shields.io/badge/Frappe-v17-blue)](https://frappeframework.com)
[![ERPNext](https://img.shields.io/badge/ERPNext-v17-green)](https://erpnext.com)

Open-source WeFact alternative built on ERPNext.

## Features

- Invoicing & Quotations (auto-numbered: FAC-2026-03-001)
- Recurring Subscriptions (monthly, quarterly, half-yearly, yearly)
- Bank Integration (Ponto API with intelligent 3-tier matching)
- Online Payments (Mollie with webhook auto-settlement)
- E-Invoicing (UBL 2.1 / Peppol BIS 3.0)
- Purchase Invoices with cost categories
- Automated Reminders & Summons
- Statistics Dashboard (revenue, costs, VAT, customer breakdown)
- Email Templates (invoices, reminders, quotes)
- Multi-company support
- Self-hosted & open-source (MIT)

## Installation

### Prerequisites

- Python 3.10+
- Node.js 18+
- MariaDB 10.6+
- Redis

### Quick Start

```bash
# Install Frappe Bench
pip install frappe-bench

# Create new site
bench init frappe-bench --frappe-branch version-15
cd frappe-bench
bench new-site nixfact.local

# Get ERPNext
bench get-app erpnext --branch version-15

# Get NIXFact
bench get-app https://github.com/NickAldewereld/erpnext-nixauce

# Install apps
bench --site nixfact.local install-app erpnext
bench --site nixfact.local install-app nixfact_integration

# Start
bench start
```

Visit: http://nixfact.local:8000

## Configuration

### 1. Settings (NixFact Instellingen)

Navigate to: **NIXFact Integration > NixFact Instellingen**

Configure:
- Invoice/Quote numbering format (prefix, year/month toggles)
- Payment terms (default: 14 days)
- Reminder settings (days, count)
- BTW percentages (default: 21%)
- Mollie API key
- Bank connection (Ponto)
- Subscription auto-invoicing

### 2. Bank Integration (Ponto)

1. Create account at https://myponto.com
2. Get OAuth2 credentials (client_id, client_secret, refresh_token)
3. Create a **NixFact Bank Koppeling** record
4. Sync transactions:

```python
frappe.call('nixfact_integration.api.bank.sync_ponto_transactions', {
    'bank_koppeling_id': 'BANK-0001'
})
```

Matching engine auto-settles at >= 95% confidence. Lower matches flagged for manual review.

### 3. Online Payments (Mollie)

1. Create account at https://mollie.com
2. Get API key from Dashboard > Developers > API keys
3. Add to NixFact Instellingen (Betaalmogelijkheden section)
4. Generate payment links:

```python
frappe.call('nixfact_integration.api.mollie.create_payment_link', {
    'factuur_name': 'FAC-2026-03-001'
})
```

Webhook auto-marks invoices as paid when customer completes payment.

### 4. UBL E-Invoicing

```python
# Generate and attach UBL XML to invoice
frappe.call('nixfact_integration.api.ubl.attach_ubl_to_factuur', {
    'factuur_name': 'FAC-2026-03-001'
})
```

## API Reference

See [docs/api.md](docs/api.md) for the full API reference.

## Architecture

```
nixfact_integration/
├── api/              # REST endpoints (bank, mollie, ubl, statistieken)
├── doctype/          # 8 DocTypes (settings, invoices, quotes, subscriptions, bank, purchases)
├── integrations/     # External APIs (Ponto, Mollie)
├── utils/            # Helpers (numbering, matching, UBL generator)
├── templates/email/  # Jinja2 email templates
└── tasks.py          # Scheduled jobs (reminders, summons, subscriptions)
```

See [docs/architecture.md](docs/architecture.md) for a technical deep-dive.

## License

MIT

## Author

Nick Aldewereld (nick@nixpay.nl)

## Contributing

PRs welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
