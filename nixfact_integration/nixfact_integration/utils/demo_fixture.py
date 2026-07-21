# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Zet een demo-factuur neer voor gesprekken met administratiekantoren.

Draaien met:
    bench --site erp.aldewereldconsultancy.nl execute \\
        nixfact_integration.utils.demo_fixture.maak_demo_factuur
"""

from __future__ import annotations

import frappe

DEMO_KLANT = "NIXFact Demo Klant B.V."


def maak_demo_factuur() -> str:
    """Maak (idempotent) een demo-klant en een meerregelige demo-factuur."""
    if not frappe.db.exists("Customer", DEMO_KLANT):
        frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": DEMO_KLANT,
                "customer_type": "Company",
                "tax_id": "NL999999999B01",
            }
        ).insert(ignore_permissions=True)

    factuur = frappe.get_doc(
        {
            "doctype": "NixFact Factuur",
            "klant": DEMO_KLANT,
            "factuur_datum": frappe.utils.nowdate(),
            "status": "Concept",
            "referentie": "DEMO-2026",
            "regels": [
                {
                    "omschrijving": "Advieswerk juli",
                    "aantal": 8,
                    "eenheidsprijs": 125.00,
                    "btw_categorie": "Standaard",
                    "btw_percentage": 21,
                },
                {
                    "omschrijving": "Licentie NIXFact (jaar)",
                    "aantal": 1,
                    "eenheidsprijs": 600.00,
                    "btw_categorie": "Standaard",
                    "btw_percentage": 21,
                },
                {
                    "omschrijving": "Doorbelasting drukwerk",
                    "aantal": 1,
                    "eenheidsprijs": 80.00,
                    "btw_categorie": "Nultarief",
                    "btw_percentage": 0,
                },
            ],
        }
    )
    factuur.insert(ignore_permissions=True)
    frappe.db.commit()
    print(
        f"[nixfact] demo-factuur {factuur.name} aangemaakt: "
        f"excl {factuur.bedrag_excl_btw}, incl {factuur.bedrag_incl_btw}"
    )
    return factuur.name
