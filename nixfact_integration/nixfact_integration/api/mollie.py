# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Whitelisted endpoints for Mollie payment links."""

from __future__ import annotations

import frappe
from frappe import _


@frappe.whitelist()
def create_payment_link(factuur_name: str) -> dict[str, str]:
    """Create (or refresh) a Mollie payment link for a NixFact Factuur.

    Permission: caller must have ``write`` on this factuur — minting a
    payment link writes back ``mollie_payment_url`` and ``betaallink``.
    """
    if not frappe.has_permission(
        "NixFact Factuur", ptype="write", doc=factuur_name, throw=False
    ):
        raise frappe.PermissionError(_("Niet toegestaan."))

    factuur = frappe.get_doc("NixFact Factuur", factuur_name)

    if factuur.status == "Betaald":
        frappe.throw(_("Deze factuur is al betaald."))

    from nixfact_integration.integrations.mollie import MollieIntegration

    mollie = MollieIntegration()

    # Re-use an existing open payment if one is still active.
    if factuur.mollie_payment_id:
        try:
            existing = mollie.get_payment(factuur.mollie_payment_id)
        except Exception:  # noqa: BLE001 — network/API hiccup → mint fresh
            existing = None
        if existing and existing.get("status") in ("open", "pending"):
            return {
                "payment_url": factuur.mollie_payment_url,
                "payment_id": factuur.mollie_payment_id,
                "message": _("Bestaande betaallink is nog actief."),
            }

    checkout_url = mollie.create_payment(factuur)
    # Re-read the now-updated factuur to return the persisted payment_id.
    payment_id = (
        frappe.db.get_value("NixFact Factuur", factuur_name, "mollie_payment_id")
        or ""
    )
    return {"payment_url": checkout_url, "payment_id": payment_id}
