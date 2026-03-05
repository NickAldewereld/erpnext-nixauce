# E-Invoicing (UBL / Peppol)

## What Is E-Invoicing?

E-invoicing means sending invoices in a structured electronic format (XML) that can be automatically processed by the recipient's accounting software. No more manual data entry!

**UBL 2.1** (Universal Business Language) is the standard format. **Peppol** is the network that delivers these invoices across Europe.

## Why Use It?

- Required by many government agencies in the Netherlands and EU
- Faster processing - no manual data entry for your customers
- Fewer errors - structured data means less mistakes
- Professional - shows you're a modern business

## Enabling E-Invoicing

1. Open **NixFact Instellingen**
2. Find **UBL e-facturatie** in the Facturatie section
3. Choose your option:
   - **Geen UBL** - disabled
   - **Alleen UBL XML** - generate XML only
   - **PDF + UBL bijlage** - attach UBL XML to your PDF invoice

## Generating a UBL Invoice

### Automatic (on save)
When enabled in settings, UBL XML is automatically generated when you save an invoice.

### Manual (via API)
```
Attach UBL to invoice:
frappe.call('nixfact_integration.api.ubl.attach_ubl_to_factuur', {
    'factuur_name': 'FAC-2026-03-001'
})
```

The XML file appears as an attachment on the invoice.

## What's in the UBL File?

The generated XML contains:
- Your company details (name, address)
- Customer details (name, address)
- Invoice number, dates, amounts
- VAT breakdown
- Line items
- Payment information

All formatted according to Peppol BIS 3.0 standards.

## Compliance

NIXFact generates UBL 2.1 XML that is:
- Peppol BIS Billing 3.0 compliant
- EN 16931 conformant (European standard)
- Ready for Dutch and EU government submission
