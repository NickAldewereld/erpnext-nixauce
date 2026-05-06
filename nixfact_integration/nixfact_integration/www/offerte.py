# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Public offerte portal — token-gated, no login required."""

from __future__ import annotations

import frappe
from frappe import _

no_cache = 1


def get_context(context):
    token = (frappe.form_dict.get("token") or "").strip()
    if not token or len(token) > 200:
        frappe.throw(_("Ongeldige link."), frappe.PermissionError)

    name = frappe.db.get_value(
        "NixFact Offerte", {"accept_token": token}, "name"
    )
    if not name:
        frappe.throw(_("Offerte niet gevonden."), frappe.DoesNotExistError)

    offerte = frappe.get_doc("NixFact Offerte", name)
    klant_naam = (
        frappe.db.get_value("Customer", offerte.klant, "customer_name")
        or offerte.klant
    )

    context.no_cache = 1
    context.show_sidebar = False
    context.offerte = offerte
    context.klant_naam = klant_naam
    context.token = token
    context.can_sign = offerte.status == "Verstuurd"
    return context
