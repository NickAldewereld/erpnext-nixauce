# Subscriptions (Abonnementen)

## Setting Up Recurring Billing

Subscriptions automatically create invoices on a schedule.

### Create a Subscription

1. Go to **NixFact Abonnement** > **+ New**
2. Select the **Klant** (customer)
3. Enter **Omschrijving** (e.g., "Website hosting maandelijks")
4. Set the **Bedrag excl. BTW**
5. Choose **Frequentie**:
   - **Maandelijks** - every month
   - **Kwartaal** - every 3 months
   - **Halfjaarlijks** - every 6 months
   - **Jaarlijks** - every 12 months
6. Set the **Startdatum** and **Volgende factuurdatum**
7. Save

### How Auto-Invoicing Works

Every day at 09:00 (configurable), NIXFact checks for subscriptions where the **Volgende factuurdatum** has arrived. For each one:

1. A new invoice is created automatically
2. The invoice status is set to **Verstuurd**
3. The subscription's **Volgende factuurdatum** advances by the frequency period

### Enabling Auto-Invoicing

In **NixFact Instellingen** > Abonnementen:
- **Automatisch factureren** must be checked
- **Dagen vooraf factureren** controls how many days early to generate (default: 1)
- **Factureren tijdstip** sets the time (default: 09:00)

### Pausing a Subscription

Set the status to **Gepauzeerd** - no invoices will be generated until you set it back to **Actief**.

### Ending a Subscription

Set an **Einddatum** or change status to **Beeindigd**. The subscription won't generate any more invoices.
