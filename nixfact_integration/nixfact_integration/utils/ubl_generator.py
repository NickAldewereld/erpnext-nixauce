# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Brug tussen NixFact Factuur en de pure UBL-laag.

Alle XML-logica zit in utils/ubl_builder.py en alle validatie in
utils/ubl_validatie.py — beide zonder frappe, zodat ze in CI testbaar
zijn. Deze module doet alleen het ophalen van gegevens en het opslaan van
de bijlage.
"""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import nowdate

from nixfact_integration.nixfact_integration.doctype.nixfact_factuur import (
    nixfact_factuur,
)
from nixfact_integration.utils.ubl_builder import build_invoice_xml
from nixfact_integration.utils.ubl_model import UBLFactuur, UBLPartij, UBLRegel
from nixfact_integration.utils.ubl_validatie import valideer

# Sanitize filename — keep alnum/dash/underscore only.
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-]")


def factuur_naar_model(factuur_name: str) -> UBLFactuur:
    """Haal een factuur op en vertaal hem naar het pure UBL-datamodel."""
    return model_uit_doc(frappe.get_doc("NixFact Factuur", factuur_name))


def model_uit_doc(factuur) -> UBLFactuur:
    """Vertaal een reeds geladen factuurdocument naar het UBL-datamodel.

    Neemt bewust het document en niet de naam: de validatiehook draait
    vóór het opslaan, dus de regels in de database zijn dan nog de oude.
    """
    company_name = factuur.company or frappe.defaults.get_defaults().get("company")
    if not company_name:
        frappe.throw(
            _(
                "Geen 'company' op de factuur en geen default company ingesteld; "
                "kan geen UBL genereren."
            )
        )
    if not factuur.klant:
        frappe.throw(_("Factuur heeft geen klant; kan geen UBL genereren."))

    company = frappe.get_doc("Company", company_name)
    customer = frappe.get_doc("Customer", factuur.klant)
    iban, bic = _get_company_bank(company_name)

    regels = [
        UBLRegel(
            omschrijving=r["omschrijving"],
            aantal=r["aantal"],
            eenheidsprijs=r["eenheidsprijs"],
            excl=r["excl"],
            btw_percentage=r["btw_percentage"],
            btw_code=r["btw_code"],
        )
        for r in nixfact_factuur.regels_als_dicts(factuur)
    ]

    return UBLFactuur(
        nummer=factuur.factuurnummer or factuur.name,
        factuurdatum=str(factuur.factuur_datum or nowdate()),
        vervaldatum=str(factuur.vervaldatum or ""),
        referentie=factuur.referentie or "",
        leverancier=_partij_uit_entiteit(
            company, _get_primary_address(company_name, "Company")
        ),
        afnemer=_partij_uit_entiteit(
            customer, _get_primary_address(factuur.klant, "Customer")
        ),
        regels=regels,
        iban=iban or "",
        bic=bic or "",
        betaald_bedrag=float(factuur.betaald_bedrag or 0),
        opmerkingen=factuur.opmerkingen or "",
    )


def _partij_uit_entiteit(entity, address: dict) -> UBLPartij:
    """Vertaal een Company- of Customer-document naar een UBLPartij."""
    naam = (
        getattr(entity, "company_name", None)
        or getattr(entity, "customer_name", None)
        or getattr(entity, "name", "")
        or ""
    )
    return UBLPartij(
        naam=naam,
        btw_nummer=(getattr(entity, "tax_id", None) or "").strip(),
        straat=address.get("address_line1", ""),
        extra_straat=address.get("address_line2", ""),
        plaats=address.get("city", ""),
        postcode=address.get("pincode", ""),
        landcode=address.get("country_code", "NL"),
        email=getattr(entity, "email_id", "") or "",
        telefoon=getattr(entity, "phone_no", "") or "",
    )


def generate_ubl_invoice(factuur_name: str) -> str:
    """Genereer een UBL 2.1 / Peppol BIS 3.0 Invoice XML-string."""
    return build_invoice_xml(factuur_naar_model(factuur_name))


def valideer_factuur_doc(doc, method=None) -> None:
    """Hook: blokkeer het versturen van een factuur die niet geldig is.

    Draait alleen bij de overgang naar 'Verstuurd' — een concept mag
    onvolledig zijn, dat is het punt van een concept.
    """
    # Schaduwmodus: WeFact-eigendom wordt nooit door NIXFact gevalideerd
    # of verstuurd — historische administratie, nooit via Peppol gegaan.
    if doc.get("wefact_identifier") if hasattr(doc, "get") else getattr(
        doc, "wefact_identifier", None
    ):
        return

    if doc.status != "Verstuurd":
        return
    vorige = doc.get_doc_before_save()
    if vorige and vorige.status == "Verstuurd":
        return

    fouten = valideer(model_uit_doc(doc))
    if not fouten:
        return

    regels = "".join(f"<li>{frappe.utils.escape_html(f.melding)}</li>"
                     for f in fouten)
    frappe.throw(
        _("Deze factuur voldoet nog niet aan de e-facturatie-eisen:")
        + f"<ul>{regels}</ul>",
        frappe.ValidationError,
    )


def generate_and_attach_ubl(factuur_name: str) -> str:
    """Genereer UBL XML, hang die als privébestand aan de factuur.

    Idempotent: opnieuw draaien vervangt de bestaande bijlage.
    """
    xml_content = generate_ubl_invoice(factuur_name)
    factuur = frappe.get_doc("NixFact Factuur", factuur_name)

    raw = factuur.factuurnummer or factuur.name
    safe = _SAFE_FILENAME_RE.sub("_", raw)
    filename = f"{safe}.xml"

    existing = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "NixFact Factuur",
            "attached_to_name": factuur_name,
            "file_name": filename,
        },
        pluck="name",
    )
    for old in existing:
        try:
            frappe.delete_doc("File", old, ignore_permissions=True)
        except Exception:  # noqa: BLE001
            frappe.log_error(
                title="UBL: kon oude bijlage niet verwijderen",
                message=frappe.get_traceback(),
            )

    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": filename,
            "attached_to_doctype": "NixFact Factuur",
            "attached_to_name": factuur_name,
            "content": xml_content,
            "is_private": 1,
        }
    )
    file_doc.save(ignore_permissions=True)
    frappe.db.commit()
    return file_doc.file_url


# --------------------------------------------------------------------------
# Address & bank-account helpers
# --------------------------------------------------------------------------


def _get_primary_address(party_name: str, party_type: str) -> dict:
    """Return the primary address for a Customer/Company, or {}."""
    address_name = frappe.db.sql(
        """
        SELECT dl.parent
        FROM `tabDynamic Link` dl
        LEFT JOIN `tabAddress` a ON a.name = dl.parent
        WHERE dl.link_doctype = %s
          AND dl.link_name = %s
          AND dl.parenttype = 'Address'
        ORDER BY a.is_primary_address DESC, a.creation ASC
        LIMIT 1
        """,
        (party_type, party_name),
        as_list=True,
    )
    if not address_name:
        return {}

    addr = frappe.get_doc("Address", address_name[0][0])
    country_code = "NL"
    if addr.country:
        country_code = (
            frappe.db.get_value("Country", addr.country, "code") or "NL"
        )

    return {
        "address_line1": addr.address_line1 or "",
        "address_line2": addr.address_line2 or "",
        "city": addr.city or "",
        "pincode": addr.pincode or "",
        "country_code": country_code.upper(),
    }


def _get_company_bank(company_name: str) -> tuple[str | None, str | None]:
    """Return (iban, bic) for the default company Bank Account, or (None, None)."""
    if not company_name:
        return None, None

    row = frappe.db.sql(
        """
        SELECT iban, swift_number
        FROM `tabBank Account`
        WHERE party_type = 'Company'
          AND party = %s
          AND iban IS NOT NULL
          AND iban != ''
        ORDER BY is_default DESC, creation ASC
        LIMIT 1
        """,
        (company_name,),
        as_list=True,
    )
    if not row:
        return None, None

    iban = (row[0][0] or "").replace(" ", "").upper() or None
    bic = (row[0][1] or "").strip() or None
    return iban, bic
