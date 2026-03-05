# Purchase Invoices (Inkoopfacturen)

## Recording a Supplier Invoice

When you receive an invoice from a supplier:

1. Go to **NixFact Inkoopfactuur** > **+ New**
2. Select the **Leverancier** (supplier)
3. Enter the **Bedrag excl. BTW** - VAT is calculated automatically
4. Set the **Factuurdatum**
5. Upload the **Document** (PDF or photo of the invoice)
6. Optionally assign a **Kostencategorie** and **Project**
7. Save

The invoice gets an automatic number like `INK-2026-03-001`.

## Statuses

| Status | Meaning |
|--------|---------|
| **Te verwerken** | New, needs to be reviewed and booked |
| **Geboekt** | Reviewed and entered in the books |
| **Betaald** | Payment made to the supplier |

## Cost Categories

Organize your expenses with categories:

1. Go to **NixFact Kostencategorie** > **+ New**
2. Enter a **Categorie** name (e.g., "Hosting", "Office", "Software")
3. Optionally add a **Code** and **Grootboekrekening** (ledger account)
4. Save

Now you can assign categories to purchase invoices for better expense tracking.

## Project Tracking

Link purchase invoices to projects to track project costs:
1. Create a **Project** in ERPNext
2. Select it in the **Project** field on the purchase invoice

## Expense Reporting

Use the Statistics dashboard to see:
- Total costs per period
- Costs broken down by category
- Costs per project
