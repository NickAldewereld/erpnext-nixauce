# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Voeg WeFact-koppelvelden toe aan Supplier."""

from __future__ import annotations


def custom_field_specs() -> dict:
    return {
        "Supplier": [
            {"fieldname": "wefact_identifier", "label": "WeFact ID",
             "fieldtype": "Data", "read_only": 1, "search_index": 1,
             "insert_after": "supplier_name"},
            {"fieldname": "wefact_creditor_code", "label": "WeFact crediteurcode",
             "fieldtype": "Data", "read_only": 1, "search_index": 1,
             "insert_after": "wefact_identifier"},
        ],
    }


def execute() -> None:
    import frappe
    from frappe.custom.doctype.custom_field.custom_field import (
        create_custom_fields,
    )

    create_custom_fields(custom_field_specs(), ignore_validate=True)
    frappe.db.commit()
    print("[nixfact] WeFact custom fields aangemaakt op Supplier")
