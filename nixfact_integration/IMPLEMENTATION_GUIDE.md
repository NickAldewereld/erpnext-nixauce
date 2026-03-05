# NIXFact - Complete Implementation Guide
## ERPNext-based WeFact Alternative (erpnext-nixauce fork)

**Repository**: `github.com/NickAldewereld/erpnext-nixauce`  
**Base**: ERPNext fork  
**Goal**: Complete open-source invoicing system  
**License**: MIT

---

## 🎯 Project Overview

Building a self-hosted, WeFact-inspired invoicing system on ERPNext with:

✅ Invoicing & Quotations  
✅ Recurring subscriptions (25 active in WeFact)  
✅ Purchase invoice management (851 queue in WeFact)  
✅ Bank transaction matching (88 unprocessed, Ponto integration)  
✅ Multi-user support  
✅ Email automation  
✅ UBL 2.1 / Peppol e-invoicing  
✅ Statistics & dashboards (5 tabs)  
✅ Payment integrations (Mollie, SEPA)  

---

## 📋 Complete Feature Matrix

Based on 30+ WeFact screenshots:

### Core Modules
1. **Settings** ⚙️ - Foundation (BUILD FIRST!)
2. **Offertes** - Partially done
3. **Facturen** - Partially done  
4. **Abonnementen** - Recurring billing
5. **Inkoopfacturen** - Purchase invoices
6. **Bank** - Transactions & matching
7. **Relaties** - CRM (255 customers, 84 suppliers)
8. **Taken** - Tasks
9. **Producten** - Products (48 items, 4 groups, inventory)
10. **Statistieken** - Analytics (5 tabs)
11. **Medewerkers** - Users

---

## 🚀 SPRINT ROADMAP

### **SPRINT 0: Settings Foundation (Week 1) - START HERE**

**Why first?** All modules depend on settings for:
- Numbering formats
- Payment terms
- Email automation
- BTW rates

**Create**: `NixFactInstellingen` (Singleton DocType)

**Key Fields**:
```
Algemeen:
- standaard_verzendmethode (Email/Post)
- prijzen_inclusief_btw
- resultaten_per_pagina (100)
- dagelijkse_email_notificatie

Nummering:
- factuur_voorvoegsel ("FAC")
- factuur_volgnummer (1)
- gebruik_jaar_factuur (✓)
- gebruik_maand_factuur
- offerte_voorvoegsel ("OFF")

Facturatie:
- betalingstermijn_facturen (14 dagen)
- ubl_inschakelen (PDF + UBL options)
- pdf_bijlagen_samenvoegen

Herinneringen:
- betalingstermijn_herinnering (7 dagen)
- betalingstermijn_aanmaning (7 dagen)
- aantal_herinneringen (1)
- negatief_openstaand_blokkeren

Offertes:
- geldigheid_offertes (30 dagen)
- offerte_accept_notificatie_email
- auto_verstuur_accept_bevestiging

Abonnementen:
- abonnement_vooraf_dagen (1)
- auto_factureren_abonnementen (✓)
- factureren_tijdstip (09:00)
- samenvoegen_zelfde_datum

Inkoop:
- inkoop_ontvangstbevestiging
- inkoop_uitgaven_specificeren

BTW:
- standaard_verkoop_btw (21%)
- standaard_inkoop_btw (21%)

Betaalmogelijkheden:
- mollie_enabled
- mollie_api_key
- sepa_incasso_enabled

Bank:
- bankkoppeling_toestaan (✓)
- transacties_verwijderen
- automatisch_matchen
```

---

### **SPRINT 1: Auto-Numbering (Week 1)**

**File**: `nixfact_integration/utils/numbering.py`

```python
def get_next_nummer(doctype, prefix_field, counter_field):
    """
    Generate: FAC-2026-03-001
    
    Supports formats:
    - FAC-2026-03-001 (year + month)
    - FAC-2026-001 (year only)
    - FAC-001 (simple)
    """
    settings = frappe.get_single("NixFactInstellingen")
    prefix = getattr(settings, prefix_field)
    
    # Build pattern based on settings
    # Query last number
    # Increment
    # Return formatted string
```

**Usage in DocType**:
```python
class NixFactFactuur(Document):
    def autoname(self):
        from nixfact_integration.utils.numbering import set_nummer_for_doc
        set_nummer_for_doc(self, 'NixFactFactuur')
        self.name = self.factuurnummer
```

---

### **SPRINT 2: Scheduled Jobs (Week 2)**

**File**: `nixfact_integration/tasks.py`

```python
def verstuur_herinneringen():
    """Daily: Send payment reminders"""
    settings = frappe.get_single("NixFactInstellingen")
    termijn = settings.betalingstermijn_herinnering
    
    # Find overdue facturen
    # Send reminder emails
    # Mark herinnering_1_verstuurd = True

def verstuur_aanmaningen():
    """Daily: Send payment summons"""
    # Similar logic for aanmaningen

def genereer_abonnement_facturen():
    """09:00 daily: Generate subscription invoices"""
    settings = frappe.get_single("NixFactInstellingen")
    
    if not settings.auto_factureren_abonnementen:
        return
    
    # Find abonnementen with volgende_factuur_datum = today
    # Create facturen
    # Update volgende_factuur_datum
```

**Register in hooks.py**:
```python
scheduler_events = {
    "daily": [
        "nixfact_integration.tasks.verstuur_herinneringen",
        "nixfact_integration.tasks.verstuur_aanmaningen"
    ],
    "cron": {
        "0 9 * * *": [
            "nixfact_integration.tasks.genereer_abonnement_facturen"
        ]
    }
}
```

---

### **SPRINT 3: Bank Integration (Week 3-4)**

**Ponto API**: `nixfact_integration/integrations/ponto.py`

```python
class PontoIntegration:
    BASE_URL = "https://api.myponto.com"
    
    def get_transactions(self, account_id, from_date, to_date):
        """Fetch transactions from Ponto"""
        # OAuth2 authentication
        # GET /accounts/{id}/transactions
        # Parse response
        # Return standardized format
```

**Matching Algorithm**: `nixfact_integration/utils/bank_matching.py`

```python
def match_transaction(transaction):
    """
    Match strategies (in order):
    
    1. Extract factuurnummer from omschrijving
       Confidence: 100%
    
    2. Match bedrag + klant + datum (±7 days)
       Confidence: 90-95%
    
    3. Fuzzy naam match
       Confidence: 60-80%
    """
    
    # Strategy 1: Regex patterns
    patterns = [
        r'(FAC-?\d{4}-?\d{2}-?\d{3,4})',
        r'(OFF-?\d{4}-?\d{2}-?\d{3,4})'
    ]
    
    # Strategy 2: Query facturen with matching bedrag
    # Check date proximity + klant similarity
    
    # Strategy 3: Fuzzy match on all openstaande
    # Use SequenceMatcher for string similarity

def auto_afletteren(transaction, factuur):
    """Auto-match at >95% confidence"""
    factuur.status = "Betaald"
    factuur.betaald_bedrag = transaction.bedrag
    transaction.status = "Afgeleterd"
```

---

### **SPRINT 4: Mollie Integration (Week 5)**

**File**: `nixfact_integration/integrations/mollie.py`

```python
def create_payment(factuur):
    """Generate payment link"""
    response = requests.post(
        "https://api.mollie.com/v2/payments",
        json={
            "amount": {"currency": "EUR", "value": f"{factuur.bedrag_incl_btw:.2f}"},
            "description": f"Factuur {factuur.factuurnummer}",
            "webhookUrl": "/api/method/nixfact.mollie.webhook"
        }
    )
    return response.json()["_links"]["checkout"]["href"]

@frappe.whitelist(allow_guest=True)
def webhook():
    """Handle payment status updates"""
    # Mollie calls this when payment completes
    # Mark factuur as betaald
```

---

### **SPRINT 5: UBL 2.1 Generation (Week 6)**

**File**: `nixfact_integration/utils/ubl_generator.py`

```python
def generate_ubl_invoice(factuur):
    """Generate UBL 2.1 XML"""
    from lxml import etree
    
    nsmap = {
        None: "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
        "cac": "...CommonAggregateComponents-2",
        "cbc": "...CommonBasicComponents-2"
    }
    
    invoice = etree.Element("Invoice", nsmap=nsmap)
    
    # Add UBL structure:
    # - Invoice number
    # - Dates
    # - Parties (supplier/customer)
    # - Tax totals
    # - Line items
    
    return etree.tostring(invoice, pretty_print=True)
```

---

## 📂 Repository Structure

```
erpnext-nixauce/
├── apps/
│   ├── erpnext/              # Forked ERPNext
│   └── nixfact_integration/  # Custom app
│       └── nixfact_integration/
│           ├── api/
│           │   ├── offerte.py
│           │   ├── factuur.py
│           │   ├── abonnement.py
│           │   └── statistieken.py
│           ├── doctype/
│           │   ├── nixfact_instellingen/
│           │   ├── nixfact_offerte/
│           │   ├── nixfact_factuur/
│           │   ├── nixfact_abonnement/
│           │   ├── nixfact_bank_transactie/
│           │   └── nixfact_inkoopfactuur/
│           ├── integrations/
│           │   ├── ponto.py
│           │   ├── mollie.py
│           │   └── peppol.py
│           ├── utils/
│           │   ├── numbering.py
│           │   ├── bank_matching.py
│           │   ├── ubl_generator.py
│           │   └── email.py
│           ├── templates/
│           │   ├── email/
│           │   └── print/
│           ├── tasks.py
│           └── hooks.py
```

---

## 🔧 Setup Commands

```bash
# Navigate to bench
cd ~/frappe-bench

# Install app (if not already)
bench --site nixfact.eu install-app nixfact_integration

# Migrate database
bench --site nixfact.eu migrate

# Enable scheduler
bench enable-scheduler

# Restart
bench restart

# Watch logs
bench --site nixfact.eu watch
```

---

## ✅ Progress Checklist

**SPRINT 0: Settings**
- [ ] NixFactInstellingen DocType created
- [ ] All settings fields added
- [ ] Settings UI accessible
- [ ] Default values working

**SPRINT 1: Numbering**
- [ ] Auto-numbering utility created
- [ ] Offertes auto-numbered
- [ ] Facturen auto-numbered
- [ ] Format configurable via settings

**SPRINT 2: Automation**
- [ ] Scheduled jobs registered in hooks.py
- [ ] Herinneringen sending daily
- [ ] Aanmaningen sending daily
- [ ] Abonnementen auto-creating facturen at 09:00

**SPRINT 3: Bank**
- [ ] Ponto integration complete
- [ ] Transactions syncing
- [ ] Matching algorithm working
- [ ] Auto-afletteren at >95%
- [ ] UI for manual matching

**SPRINT 4: Payments**
- [ ] Mollie API integration
- [ ] Payment links in emails
- [ ] Webhook handling payments
- [ ] Facturen auto-marked as paid

**SPRINT 5: E-Invoicing**
- [ ] UBL 2.1 XML generation
- [ ] PDF + UBL combined
- [ ] Peppol ready

---

## 🐛 Common Issues & Solutions

**Auto-numbering not working:**
- Check NixFactInstellingen singleton exists
- Verify fields have default values
- Ensure autoname() is called
- Debug with `frappe.log_error()`

**Scheduled jobs not running:**
- Enable scheduler: `bench enable-scheduler`
- Check hooks.py registration
- Verify task function exists
- Check scheduler logs

**Email not sending:**
- Configure SMTP in ERPNext settings
- Check email templates exist
- View email queue: Desk > Email Queue
- Enable outgoing email

**Permissions errors:**
- Add `ignore_permissions=True` to system operations
- Check DocType permissions
- Grant System Manager role

**Ponto API errors:**
- Verify client_id and client_secret
- Check refresh_token is valid
- Confirm account_id is correct
- Review Ponto API logs

---

## 📚 Resources

- **Frappe Docs**: https://frappeframework.com/docs
- **ERPNext Docs**: https://docs.erpnext.com
- **WeFact API**: https://www.wefact.nl/help/api
- **Ponto API**: https://documentation.myponto.com
- **UBL 2.1**: https://docs.peppol.eu/poacc/billing/3.0/
- **Mollie API**: https://docs.mollie.com/

---

## 🎯 Definition of Done

Feature is complete when:

1. ✅ Code written and committed
2. ✅ DocTypes migrated
3. ✅ API endpoints tested
4. ✅ UI functional
5. ✅ Error handling implemented
6. ✅ No breaking changes
7. ✅ Documentation updated

---

## 📞 Contact & Support

**Nick Aldewereld**  
Email: nick@nixpay.nl  
GitHub: github.com/NickAldewereld/erpnext-nixauce  

---

**Status**: Ready for Claude Code implementation  
**Version**: 1.0  
**Last Updated**: March 5, 2026