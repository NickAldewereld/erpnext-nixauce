# Reports & Statistics

## Dashboard

The statistics API gives you a complete overview of your business.

### Key Metrics

| Metric | What It Shows |
|--------|--------------|
| **Totale omzet** | Total revenue (invoices sent + paid) |
| **Totale kosten** | Total expenses (purchase invoices) |
| **Resultaat** | Profit (revenue - costs) |
| **Aantal facturen** | Number of invoices |
| **Gemiddelde factuurwaarde** | Average invoice value |
| **Openstaand bedrag** | Total unpaid invoices |

### Monthly Chart

The dashboard shows a 12-month chart with:
- Revenue per month (blue)
- Costs per month (red)

This helps you spot trends and seasonal patterns.

### Top Customers

See your top 10 customers by revenue for any period.

## VAT Reporting (BTW Overzicht)

Essential for your quarterly VAT return:

The BTW report shows per quarter:
- **Verkoop excl. BTW** - total sales excluding VAT
- **Verkoop BTW** - total sales VAT collected
- **Inkoop excl. BTW** - total purchases excluding VAT
- **Inkoop BTW** - total purchase VAT paid
- **Af te dragen** - net VAT to pay (sales VAT - purchase VAT)

## Revenue by Customer

See which customers generate the most revenue:
- Number of invoices per customer
- Total revenue (excl. and incl. VAT)
- VAT breakdown

## Costs by Category

Track where your money goes:
- Expenses grouped by cost category
- Total per category (excl. and incl. VAT)
- Number of purchase invoices per category

## Accessing Reports

All reports are available via API:

```
# Dashboard
get_dashboard_data(periode='maand', jaar=2026, maand=3)

# VAT
get_btw_overzicht(kwartaal=1, jaar=2026)

# Revenue by customer
get_omzet_per_klant(jaar=2026)

# Costs by category
get_kosten_per_categorie(jaar=2026)
```
