# Quotations (Offertes)

## Creating a Quote

1. Go to **NixFact Offerte** > **+ New**
2. Select the **Klant** (customer)
3. Enter amounts (**Bedrag excl. BTW** and **Bedrag incl. BTW**)
4. Add a **Referentie** (description of what you're quoting)
5. Save - the quote gets an automatic number like `OFF-2026-03-001`

## Quote Statuses

| Status | Meaning |
|--------|---------|
| **Geaccepteerd** | Customer accepted the quote |
| **Geweigerd** | Customer declined |
| **Factuur aangemaakt** | Quote converted to invoice |

## Converting a Quote to an Invoice

When a customer accepts your quote:

1. Open the quote
2. Change status to **Geaccepteerd**
3. Create a new **NixFact Factuur** with the same amounts
4. Update the quote status to **Factuur aangemaakt**

## Quote Validity

Quotes have a validity period (default: 30 days, configurable in Settings). This helps you track which quotes need follow-up.

## Acceptance Notifications

In **NixFact Instellingen**, you can enable:
- **Email notificatie bij acceptatie** - get notified when a quote is accepted
- **Automatisch acceptatiebevestiging** - auto-send a confirmation to the customer
