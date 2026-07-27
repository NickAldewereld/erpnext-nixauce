# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Idempotente ORM-laag voor de WeFact-import. Enige die de DB raakt."""

from __future__ import annotations

import frappe

ALDEWERELD = "Aldewereld Consultancy"


def ensure_company(naam: str = ALDEWERELD) -> str:
    """Maak (idempotent) de doelcompany aan als hij nog niet bestaat."""
    if frappe.db.exists("Company", naam):
        return naam
    frappe.get_doc(
        {
            "doctype": "Company",
            "company_name": naam,
            "default_currency": "EUR",
            "country": "Netherlands",
            "tax_id": "NL002168402B79",
        }
    ).insert(ignore_permissions=True)
    frappe.db.commit()
    return naam


def _find_by_wefact_id(doctype: str, wefact_id: str) -> str | None:
    if not wefact_id:
        return None
    return frappe.db.get_value(doctype, {"wefact_identifier": wefact_id}, "name")


def upsert_customer(customer: dict, address: dict | None) -> str:
    """Maak of werk een Customer bij, gekoppeld op wefact_identifier."""
    bestaand = _find_by_wefact_id("Customer", customer["wefact_identifier"])
    if bestaand:
        doc = frappe.get_doc("Customer", bestaand)
        doc.update(customer)
    else:
        doc = frappe.get_doc({"doctype": "Customer", **customer})
    doc.save(ignore_permissions=True)

    if address:
        _upsert_address(doc.name, customer, address)
    frappe.db.commit()
    return doc.name


def _upsert_address(customer_name: str, customer: dict, address: dict) -> None:
    titel = f"{customer['wefact_identifier']}-WeFact"
    bestaand = frappe.db.get_value("Address", {"address_title": titel}, "name")
    velden = {
        "address_line1": address["address_line1"] or "-",
        "city": address["city"] or "-",
        "pincode": address["pincode"],
        "country": _land_uit_code(address["country_code"]),
    }
    if bestaand:
        adoc = frappe.get_doc("Address", bestaand)
        adoc.update(velden)
    else:
        adoc = frappe.get_doc(
            {
                "doctype": "Address",
                "address_title": titel,
                "address_type": "Billing",
                "links": [
                    {"link_doctype": "Customer", "link_name": customer_name}
                ],
                **velden,
            }
        )
    adoc.save(ignore_permissions=True)


def _land_uit_code(code: str) -> str:
    naam = frappe.db.get_value("Country", {"code": (code or "nl").lower()}, "name")
    return naam or "Netherlands"


def upsert_factuur(factuur: dict, company: str) -> str:
    """Maak of werk een NixFact Factuur bij, gekoppeld op wefact_identifier."""
    klant = frappe.db.get_value(
        "Customer", {"wefact_debtor_code": factuur["wefact_debtor_code"]}, "name"
    )
    if not klant:
        raise ValueError(
            f"Geen klant voor debiteurcode {factuur['wefact_debtor_code']}"
        )
    if not factuur["factuur_datum"]:
        raise ValueError(f"Factuur {factuur['factuurnummer']} heeft geen datum")

    kop = {
        "klant": klant,
        "company": company,
        "factuurnummer": factuur["factuurnummer"],
        "factuur_datum": factuur["factuur_datum"],
        "referentie": factuur["referentie"],
        "status": factuur["status"],
        "wefact_identifier": factuur["wefact_identifier"],
    }
    bestaand = _find_by_wefact_id("NixFact Factuur", factuur["wefact_identifier"])
    if bestaand:
        doc = frappe.get_doc("NixFact Factuur", bestaand)
        doc.update(kop)
        doc.set("regels", [])
    else:
        doc = frappe.get_doc({"doctype": "NixFact Factuur", **kop})
    for r in factuur["regels"]:
        doc.append("regels", r)
    # Lege factuur (geen regels) mag niet — Fase 1 eist reqd regels.
    if not doc.get("regels"):
        doc.append(
            "regels",
            {
                "omschrijving": factuur["factuurnummer"] or "WeFact-import",
                "aantal": 1,
                "eenheidsprijs": 0,
                "btw_categorie": "Nultarief",
                "btw_percentage": 0,
            },
        )
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def upsert_supplier(supplier: dict) -> str:
    """Maak of werk een Supplier bij, gekoppeld op wefact_identifier."""
    bestaand = _find_by_wefact_id("Supplier", supplier["wefact_identifier"])
    if bestaand:
        doc = frappe.get_doc("Supplier", bestaand)
        doc.update(supplier)
    else:
        doc = frappe.get_doc({"doctype": "Supplier", **supplier})
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def upsert_creditnota(factuur: dict, company: str) -> str:
    """Upsert een verkoop-creditnota als NixFact Factuur met negatieve regels."""
    naam = upsert_factuur(factuur, company)
    doc = frappe.get_doc("NixFact Factuur", naam)
    doc.is_creditnota = 1
    doc.origineel_wefact_id = factuur.get("origineel_wefact_id") or ""
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return naam
