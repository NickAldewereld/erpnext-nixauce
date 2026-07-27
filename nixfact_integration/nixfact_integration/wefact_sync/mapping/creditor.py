# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-crediteur → ERPNext Supplier-dict. Puur."""

from __future__ import annotations


def creditor_to_supplier(wf: dict) -> dict:
    naam = (wf.get("CompanyName") or "").strip()
    code = (wf.get("CreditorCode") or "").strip()
    return {
        "supplier_name": naam or f"WeFact {code or wf.get('Identifier')}",
        "tax_id": (wf.get("TaxNumber") or "").strip(),
        "wefact_identifier": str(wf.get("Identifier") or ""),
        "wefact_creditor_code": code,
    }
