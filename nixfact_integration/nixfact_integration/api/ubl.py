# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Whitelisted endpoints for UBL e-invoicing."""

from __future__ import annotations

import frappe
from frappe import _


@frappe.whitelist()
def generate_ubl_xml(factuur_name: str) -> dict:
    """Generate UBL 2.1 XML for an invoice and return it inline.

    Permission: caller must have ``read`` on this factuur — the XML
    contains supplier + customer PII.
    """
    if not frappe.has_permission(
        "NixFact Factuur", ptype="read", doc=factuur_name, throw=False
    ):
        raise frappe.PermissionError(_("Niet toegestaan."))

    from nixfact_integration.utils.ubl_generator import generate_ubl_invoice

    xml = generate_ubl_invoice(factuur_name)
    factuurnummer = frappe.db.get_value("NixFact Factuur", factuur_name, "factuurnummer")
    return {"xml": xml, "factuurnummer": factuurnummer}


@frappe.whitelist()
def attach_ubl_to_factuur(factuur_name: str) -> dict:
    """Generate UBL XML and attach it as a private file on the invoice.

    Permission: caller must have ``write`` on this factuur — attaching
    a file mutates the document.
    """
    if not frappe.has_permission(
        "NixFact Factuur", ptype="write", doc=factuur_name, throw=False
    ):
        raise frappe.PermissionError(_("Niet toegestaan."))

    from nixfact_integration.utils.ubl_generator import generate_and_attach_ubl

    file_url = generate_and_attach_ubl(factuur_name)
    factuurnummer = frappe.db.get_value("NixFact Factuur", factuur_name, "factuurnummer")
    return {"file_url": file_url, "factuurnummer": factuurnummer}
