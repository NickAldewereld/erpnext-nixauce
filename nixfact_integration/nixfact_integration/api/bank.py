# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Whitelisted endpoints for bank-related operations."""

from __future__ import annotations

import frappe
from frappe import _


@frappe.whitelist()
def sync_ponto_transactions(bank_koppeling_id: str) -> dict[str, int]:
    """Sync new transactions from Ponto and run the matching engine.

    Permission: caller must have ``write`` on this NixFact Bank Koppeling
    document. Without that, an unprivileged user could trigger external
    Ponto API hits and force refresh-token rotation server-side.

    Returns counts of imported / skipped / matched / auto_settled / unmatched.
    """
    if not frappe.has_permission(
        "NixFact Bank Koppeling", ptype="write", doc=bank_koppeling_id, throw=False
    ):
        raise frappe.PermissionError(_("Niet toegestaan."))

    koppeling = frappe.get_doc("NixFact Bank Koppeling", bank_koppeling_id)

    if not koppeling.actief:
        frappe.throw(_("Deze bankkoppeling is niet actief."))

    if koppeling.koppeling_type != "Ponto":
        frappe.throw(_("Deze functie is alleen beschikbaar voor Ponto koppelingen."))

    from nixfact_integration.integrations.ponto import PontoIntegration
    from nixfact_integration.utils.bank_matching import match_and_settle_all

    sync_result = PontoIntegration(koppeling).sync()
    match_result = match_and_settle_all()

    return {
        "imported": sync_result["imported"],
        "skipped": sync_result["skipped"],
        "matched": match_result["matched"],
        "auto_settled": match_result["auto_settled"],
        "unmatched": match_result["unmatched"],
    }
