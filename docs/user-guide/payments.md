# Online Payments (Mollie)

## Setting Up Mollie

Mollie lets your customers pay invoices online with iDEAL, credit card, Bancontact, and more.

### Step 1: Create a Mollie Account

1. Go to https://mollie.com and sign up
2. Complete the verification process
3. Go to Dashboard > Developers > API Keys
4. Copy your **Live API Key** (starts with `live_`)

### Step 2: Enable in NIXFact

1. Open **NixFact Instellingen**
2. Go to the **Betaalmogelijkheden** section
3. Check **Mollie inschakelen**
4. Paste your API key in **Mollie API Key**
5. Save

### Step 3: Test It

1. Create an invoice
2. Generate a payment link (via API or the desk)
3. The **Betaallink** field on the invoice shows the Mollie checkout URL

## How Payment Links Work

When you generate a payment link for an invoice:

1. NIXFact creates a payment at Mollie with the invoice amount
2. Mollie returns a checkout URL
3. The URL is saved on the invoice (in **Betaallink** and **Mollie Payment URL**)
4. You share this link with your customer (in the invoice email)

## What Happens When a Customer Pays

1. Customer clicks the payment link
2. They pay via their preferred method (iDEAL, credit card, etc.)
3. Mollie sends a webhook to NIXFact
4. NIXFact verifies the payment status with Mollie
5. If paid: invoice is automatically marked as **Betaald**

This all happens within seconds - no manual work needed!

## Payment Statuses

| Mollie Status | NIXFact Action |
|---------------|----------------|
| `paid` | Invoice marked as Betaald |
| `failed` | No change (customer can retry) |
| `expired` | No change (generate new link) |
| `canceled` | No change |

## Including Payment Links in Emails

The email templates include a "Nu betalen" (Pay Now) button that links to the Mollie checkout. This only appears when a payment link exists on the invoice.

## Duplicate Prevention

If you try to generate a new payment link for an invoice that already has an active one, NIXFact returns the existing link instead of creating a duplicate.
