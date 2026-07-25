# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Voeg WeFact-koppelvelden toe aan Customer.

`custom_field_specs` is puur zodat de vorm in CI te testen is; `execute`
past ze toe via de Frappe custom-field-API. De config-velden op NixFact
Instellingen zitten in de doctype-JSON en syncen vanzelf mee bij migrate.
"""

from __future__ import annotations


def custom_field_specs() -> dict:
    """Custom-Field-definities per doctype (ERPNext-standaarddoctypes)."""
    return {
        "Customer": [
            {
                "fieldname": "wefact_identifier",
                "label": "WeFact ID",
                "fieldtype": "Data",
                "read_only": 1,
                "search_index": 1,
                "insert_after": "customer_name",
            },
            {
                "fieldname": "wefact_debtor_code",
                "label": "WeFact debiteurcode",
                "fieldtype": "Data",
                "read_only": 1,
                "search_index": 1,
                "insert_after": "wefact_identifier",
            },
        ],
    }


def execute() -> None:
    """Maak custom fields op Customer."""
    import frappe
    from frappe.custom.doctype.custom_field.custom_field import (
        create_custom_fields,
    )

    create_custom_fields(custom_field_specs(), ignore_validate=True)
    frappe.db.commit()
    print("[nixfact] WeFact custom fields aangemaakt op Customer")
