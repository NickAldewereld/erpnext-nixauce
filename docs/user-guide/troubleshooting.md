# Troubleshooting

## Common Issues

### Invoices aren't being auto-numbered

**Check:**
1. Open **NixFact Instellingen** and verify the numbering fields have values
2. Make sure the **voorvoegsel** (prefix) is filled in
3. Check that **volgnummer** (counter) is at least 1

### Reminders aren't being sent

**Check:**
1. Run `bench enable-scheduler` on the server
2. Verify scheduler is running: `bench doctor`
3. Check the **Herinneringen** section in NixFact Instellingen
4. Invoices must have status **Verstuurd** and be past the due date

### Bank sync doesn't work

**Check:**
1. Open your **NixFact Bank Koppeling** and verify credentials
2. Make sure **Actief** is checked
3. Check that the Ponto refresh token hasn't expired
4. View error logs in ERPNext > Error Log

### Mollie payments not processing

**Check:**
1. Verify **Mollie inschakelen** is checked in settings
2. Check the API key is correct (starts with `live_` for production)
3. Ensure your site URL is publicly accessible (Mollie needs to reach the webhook)
4. Check ERPNext Error Log for webhook failures

### VAT calculations are wrong

**Check:**
1. Verify **BTW %** on the invoice (default comes from settings)
2. Make sure **Bedrag excl. BTW** is entered correctly
3. BTW bedrag and Bedrag incl. BTW are calculated automatically

### UBL XML not generating

**Check:**
1. Ensure `lxml` is installed: `pip install lxml`
2. Check **UBL e-facturatie** setting is not "Geen UBL"
3. The invoice needs at least: factuurnummer, factuur_datum, bedrag_excl_btw

## FAQ

**Q: Can I change an invoice number after creation?**
A: No, invoice numbers are auto-generated and permanent. This ensures audit compliance.

**Q: What happens if I delete a subscription?**
A: Existing invoices generated from the subscription remain. Only future invoices stop.

**Q: Can I use NIXFact with multiple companies?**
A: Yes! Each invoice, quote, and subscription has a **Bedrijf** (Company) field.

**Q: Is my Mollie API key stored securely?**
A: Yes, it's stored as a Frappe Password field, which is encrypted in the database.

**Q: How do I export data?**
A: Use the built-in ERPNext export feature on any list view (CSV, Excel).

**Q: Can I customize the email templates?**
A: Yes, the templates are Jinja2 HTML files in `templates/email/`.

## Getting Help

- **Email**: nick@nixpay.nl
- **GitHub**: https://github.com/NickAldewereld/erpnext-nixauce/issues
- **Error Logs**: Check ERPNext > Error Log for technical details
