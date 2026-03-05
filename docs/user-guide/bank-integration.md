# Bank Integration

## Connecting Your Bank (Ponto)

NIXFact uses Ponto (by Isabel Group) to connect to Dutch and Belgian banks.

### Step 1: Create a Ponto Account

1. Go to https://myponto.com and sign up
2. Connect your bank account in the Ponto dashboard
3. Note your **Client ID**, **Client Secret**, and **Account ID**
4. Generate a **Refresh Token** in Ponto settings

### Step 2: Set Up Bank Connection in NIXFact

1. Go to **NixFact Bank Koppeling** > **+ New**
2. Select your **Bank** (ING, Rabobank, ABN AMRO, Bunq)
3. Set **Koppeling type** to **Ponto**
4. Enter your Ponto credentials
5. Check **Actief**
6. Save

### Step 3: Sync Transactions

Click the sync button or call the API:
```
sync_ponto_transactions(bank_koppeling_id)
```

Transactions appear in **NixFact Bank Transactie** list.

## How Matching Works

NIXFact uses three strategies to match bank transactions to invoices:

### Strategy 1: Invoice Number Detection (100% confidence)

If someone includes "FAC-2026-03-001" in their payment description, NIXFact finds it instantly. This is the most reliable method.

### Strategy 2: Amount + Customer + Date (90-95% confidence)

When the exact amount matches an open invoice and the payment date is close to the due date, NIXFact is quite confident it's a match.

### Strategy 3: Fuzzy Name Matching (60-80% confidence)

NIXFact compares the payer's name to your customer names. If "J. de Vries" pays and you have customer "Jan de Vries", it finds the connection.

## Auto-Settlement

Matches with **95% or higher confidence** are automatically settled - the invoice is marked as paid and the transaction as processed.

Lower confidence matches are flagged as **Match gevonden** for you to review and confirm manually.

## Manual Matching

For unmatched transactions:
1. Open the transaction in **NixFact Bank Transactie**
2. Set **Gekoppeld aan type** to "NixFact Factuur"
3. Select the invoice in **Gekoppeld aan**
4. Change status to **Afgeleterd**
5. Save

## Tips

- Ask customers to include the invoice number in payment descriptions
- Keep customer names consistent for better fuzzy matching
- Review the **Onverwerkt** transactions regularly
