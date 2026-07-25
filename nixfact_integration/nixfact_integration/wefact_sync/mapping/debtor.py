# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-debiteur → ERPNext Customer- en Address-dict. Puur."""

from __future__ import annotations


def debtor_to_customer(wf: dict) -> dict:
    bedrijf = (wf.get("CompanyName") or "").strip()
    if bedrijf:
        naam = bedrijf
        soort = "Company"
    else:
        naam = f"{(wf.get('Initials') or '').strip()} {(wf.get('SurName') or '').strip()}".strip()
        soort = "Individual"
    return {
        "customer_name": naam or f"WeFact {wf.get('DebtorCode') or wf.get('Identifier')}",
        "customer_type": soort,
        "tax_id": (wf.get("TaxNumber") or "").strip(),
        "wefact_identifier": str(wf.get("Identifier") or ""),
        "wefact_debtor_code": (wf.get("DebtorCode") or "").strip(),
    }


def debtor_to_address(wf: dict) -> dict | None:
    straat = (wf.get("Address") or "").strip()
    stad = (wf.get("City") or "").strip()
    if not straat and not stad:
        return None
    return {
        "address_line1": straat,
        "city": stad,
        "pincode": (wf.get("ZipCode") or "").strip(),
        "country_code": (wf.get("Country") or "NL").strip().upper(),
    }
