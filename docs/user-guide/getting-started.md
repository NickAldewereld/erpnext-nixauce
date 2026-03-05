# Getting Started

## First Login

1. Open your browser and go to your NIXFact URL (e.g., `https://nixfact.yourdomain.com`)
2. Log in with the credentials your administrator provided
3. You'll see the ERPNext desk - NIXFact lives inside it

## Initial Setup

Before creating your first invoice, configure your settings:

1. Search for **NixFact Instellingen** in the search bar
2. Set your **company details** (these appear on invoices)
3. Configure **numbering** - choose your invoice prefix (default: `FAC`)
4. Set your **payment terms** (default: 14 days)
5. Set **BTW percentage** (default: 21%)
6. Click **Save**

## Creating Your First Invoice

### Step 1: Make sure you have a customer

Go to **Customer** list and create one if needed:
- Customer Name: e.g., "ACME BV"
- Customer Type: Company or Individual

### Step 2: Create the invoice

1. Search for **NixFact Factuur** and click **+ New**
2. Select your **Klant** (customer)
3. Enter the **Bedrag excl. BTW** (amount excl. VAT) - BTW is calculated automatically
4. The **Factuurdatum** defaults to today
5. The **Vervaldatum** is auto-set based on your payment terms
6. Click **Save**

Your invoice gets an automatic number like `FAC-2026-03-001`.

### Step 3: Send the invoice

Change the status from **Concept** to **Verstuurd** and save. If email is configured, the invoice will be sent to your customer.

## Recording a Payment

When a customer pays:

1. Open the invoice
2. Enter the **Betaald bedrag** (paid amount)
3. Set the **Betaaldatum** (payment date)
4. Change status to **Betaald**
5. Save

Or, if you have bank integration set up, payments are matched automatically!

## What's Next?

- [Set up bank integration](bank-integration.md) for automatic payment matching
- [Enable Mollie](payments.md) for online payment links
- [Create subscriptions](subscriptions.md) for recurring billing
