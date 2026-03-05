# API Reference

All endpoints are called via `frappe.call()` or `POST /api/method/{endpoint}`.

## Invoices (Facturen)

### Create Payment Link

```python
frappe.call('nixfact_integration.api.mollie.create_payment_link', {
    'factuur_name': 'FAC-2026-03-001'
})
```

**Returns:**
```json
{
    "payment_url": "https://www.mollie.com/checkout/...",
    "payment_id": "tr_xxx"
}
```

### Offerte CRUD

```python
# Create
frappe.call('nixfact_integration.api.create_offerte', {
    'offerte_data': {
        'klant': 'Customer Name',
        'bedrag_excl': 1000.00,
        'bedrag_incl': 1210.00,
        'offerte_datum': '2026-03-05'
    }
})

# Get
frappe.call('nixfact_integration.api.get_offerte', {
    'offerte_id': 'OFF-2026-03-001'
})

# Update status
frappe.call('nixfact_integration.api.update_offerte_status', {
    'offerte_id': 'OFF-2026-03-001',
    'status': 'Geaccepteerd'  # or: Geweigerd, Factuur aangemaakt
})
```

## Bank Integration

### Sync Transactions

```python
frappe.call('nixfact_integration.api.bank.sync_ponto_transactions', {
    'bank_koppeling_id': 'BANK-0001'
})
```

**Returns:**
```json
{
    "imported": 15,
    "skipped": 85,
    "matched": 10,
    "auto_settled": 8,
    "unmatched": 5
}
```

## UBL E-Invoicing

### Generate UBL XML

```python
frappe.call('nixfact_integration.api.ubl.generate_ubl_xml', {
    'factuur_name': 'FAC-2026-03-001'
})
```

**Returns:**
```json
{
    "xml": "<?xml version='1.0'...>",
    "factuurnummer": "FAC-2026-03-001"
}
```

### Attach UBL to Invoice

```python
frappe.call('nixfact_integration.api.ubl.attach_ubl_to_factuur', {
    'factuur_name': 'FAC-2026-03-001'
})
```

**Returns:**
```json
{
    "file_url": "/private/files/FAC-2026-03-001.xml",
    "factuurnummer": "FAC-2026-03-001"
}
```

## Statistics

### Dashboard Data

```python
frappe.call('nixfact_integration.api.statistieken.get_dashboard_data', {
    'periode': 'maand',  # maand, kwartaal, jaar
    'jaar': 2026,
    'maand': 3
})
```

**Returns:**
```json
{
    "totale_omzet": 12500.00,
    "totale_kosten": 3200.00,
    "resultaat": 9300.00,
    "aantal_facturen": 45,
    "gemiddelde_factuurwaarde": 277.78,
    "openstaand_bedrag": 5600.00,
    "grafiek_data": [
        {"maand": "jan", "omzet": 8000, "kosten": 2000}
    ],
    "top_klanten": [
        {"klant": "ACME Corp", "omzet": 5000}
    ]
}
```

### BTW Overview

```python
frappe.call('nixfact_integration.api.statistieken.get_btw_overzicht', {
    'kwartaal': 1,
    'jaar': 2026
})
```

### Revenue by Customer

```python
frappe.call('nixfact_integration.api.statistieken.get_omzet_per_klant', {
    'jaar': 2026
})
```

## Mollie Webhook

**URL:** `POST /api/method/nixfact_integration.integrations.mollie.webhook`

Called automatically by Mollie when payment status changes. Guest-accessible (no auth required). Verifies payment status with Mollie API before updating invoice.
