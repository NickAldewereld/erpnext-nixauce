# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Sync-cursor per entiteit in NixFact Instellingen.

`max_modified` is puur/testbaar; lezen/schrijven raakt frappe.
"""

from __future__ import annotations

_VELD = {
    "debtor": "wefact_cursor_debiteuren",
    "invoice": "wefact_cursor_facturen",
}


def max_modified(records: list[dict]) -> str:
    waarden = [str(r.get("Modified") or "").strip() for r in records]
    waarden = [w for w in waarden if w]
    return max(waarden) if waarden else ""


def lees_cursor(entiteit: str) -> str:
    import frappe

    veld = _VELD.get(entiteit)
    if not veld:
        return ""
    return frappe.db.get_single_value("NixFact Instellingen", veld) or ""


def schrijf_cursor(entiteit: str, waarde: str) -> None:
    import frappe

    veld = _VELD.get(entiteit)
    if not veld or not waarde:
        return
    frappe.db.set_single_value("NixFact Instellingen", veld, waarde)
    frappe.db.commit()
