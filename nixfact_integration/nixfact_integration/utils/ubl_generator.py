# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""UBL 2.1 / Peppol BIS 3.0 e-invoicing for NixFact Factuur."""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import flt, nowdate
from lxml import etree

# UBL 2.1 namespaces.
NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

NSMAP = {
    None: NS_INVOICE,
    "cac": NS_CAC,
    "cbc": NS_CBC,
}

# Peppol BIS 3.0 identifiers.
CUSTOMIZATION_ID = (
    "urn:cen.eu:en16931:2017"
    "#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
)
PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"

# Strip XML 1.0 illegal control chars (everything < 0x20 except TAB/LF/CR).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Sanitize filename — keep alnum/dash/underscore only.
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-]")


def generate_ubl_invoice(factuur_name: str) -> str:
    """Generate a UBL 2.1 / Peppol BIS 3.0 Invoice XML string."""
    factuur = frappe.get_doc("NixFact Factuur", factuur_name)

    company_name = factuur.company or frappe.defaults.get_defaults().get("company")
    if not company_name:
        frappe.throw(
            _(
                "Geen 'company' op de factuur en geen default company ingesteld; "
                "kan geen UBL genereren."
            )
        )
    company = frappe.get_doc("Company", company_name)
    company_address = _get_primary_address(company_name, "Company")
    company_iban, company_bic = _get_company_bank(company_name)

    if not factuur.klant:
        frappe.throw(_("Factuur heeft geen klant; kan geen UBL genereren."))
    customer = frappe.get_doc("Customer", factuur.klant)
    customer_address = _get_primary_address(factuur.klant, "Customer")

    invoice = etree.Element("Invoice", nsmap=NSMAP)

    _add_cbc(invoice, "CustomizationID", CUSTOMIZATION_ID)
    _add_cbc(invoice, "ProfileID", PROFILE_ID)
    _add_cbc(invoice, "ID", factuur.factuurnummer or factuur.name)
    _add_cbc(invoice, "IssueDate", str(factuur.factuur_datum or nowdate()))
    if factuur.vervaldatum:
        _add_cbc(invoice, "DueDate", str(factuur.vervaldatum))
    _add_cbc(invoice, "InvoiceTypeCode", "380")
    _add_cbc(invoice, "DocumentCurrencyCode", "EUR")
    if factuur.referentie:
        _add_cbc(invoice, "BuyerReference", factuur.referentie)

    supplier = etree.SubElement(invoice, _cac("AccountingSupplierParty"))
    _build_party(supplier, company, company_address, role="supplier")

    customer_party = etree.SubElement(invoice, _cac("AccountingCustomerParty"))
    _build_party(customer_party, customer, customer_address, role="customer")

    if company_iban:
        _build_payment_means(invoice, company_iban, company_bic, factuur)

    _build_tax_total(invoice, factuur)
    _build_monetary_total(invoice, factuur)
    _build_invoice_line(invoice, factuur)

    return etree.tostring(
        invoice,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    ).decode("utf-8")


def generate_and_attach_ubl(factuur_name: str) -> str:
    """Generate UBL XML, attach as private file, return file URL.

    Idempotent: re-running for the same factuur replaces the existing
    attachment instead of stacking duplicates.
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
# XML builder helpers
# --------------------------------------------------------------------------


def _cac(tag: str) -> str:
    return f"{{{NS_CAC}}}{tag}"


def _cbc(tag: str) -> str:
    return f"{{{NS_CBC}}}{tag}"


def _xml_safe(value: object) -> str:
    """Strip illegal XML 1.0 control chars; cast to str."""
    if value is None:
        return ""
    return _CONTROL_CHARS_RE.sub("", str(value))


def _add_cbc(parent, tag: str, text, **attribs):
    """Add a CBC element with text content. Skips when text is empty."""
    safe = _xml_safe(text)
    if not safe:
        # Don't emit empty elements — Peppol BR rules reject many.
        return None
    el = etree.SubElement(parent, _cbc(tag), **attribs)
    el.text = safe
    return el


def _add_cbc_required(parent, tag: str, text, **attribs):
    """Add a CBC element even if text is empty (for Peppol-required fields)."""
    el = etree.SubElement(parent, _cbc(tag), **attribs)
    el.text = _xml_safe(text)
    return el


def _build_party(parent_element, entity, address: dict, role: str) -> None:
    """Build AccountingSupplierParty.Party or AccountingCustomerParty.Party.

    Includes the Peppol BIS 3.0 mandatories: EndpointID, PartyName,
    PostalAddress, PartyTaxScheme (if VAT registered), PartyLegalEntity.
    """
    party = etree.SubElement(parent_element, _cac("Party"))

    tax_id = (getattr(entity, "tax_id", None) or "").strip()
    if tax_id:
        endpoint = etree.SubElement(party, _cbc("EndpointID"), schemeID="9944")
        endpoint.text = _xml_safe(tax_id)

    party_name_el = etree.SubElement(party, _cac("PartyName"))
    name = (
        getattr(entity, "company_name", None)
        or getattr(entity, "customer_name", None)
        or getattr(entity, "name", "")
        or ""
    )
    _add_cbc_required(party_name_el, "Name", name)

    postal = etree.SubElement(party, _cac("PostalAddress"))
    _add_cbc(postal, "StreetName", address.get("address_line1", ""))
    _add_cbc(postal, "AdditionalStreetName", address.get("address_line2", ""))
    _add_cbc(postal, "CityName", address.get("city", ""))
    _add_cbc(postal, "PostalZone", address.get("pincode", ""))
    country_el = etree.SubElement(postal, _cac("Country"))
    _add_cbc_required(
        country_el,
        "IdentificationCode",
        address.get("country_code", "NL"),
        listID="ISO3166-1:Alpha2",
    )

    if tax_id:
        tax_scheme_el = etree.SubElement(party, _cac("PartyTaxScheme"))
        _add_cbc_required(tax_scheme_el, "CompanyID", tax_id)
        scheme = etree.SubElement(tax_scheme_el, _cac("TaxScheme"))
        _add_cbc_required(scheme, "ID", "VAT")

    legal = etree.SubElement(party, _cac("PartyLegalEntity"))
    _add_cbc_required(legal, "RegistrationName", name)
    if tax_id:
        _add_cbc(legal, "CompanyID", tax_id)

    contact = etree.SubElement(party, _cac("Contact"))
    contact_name = (
        getattr(entity, "contact_person", None)
        or getattr(entity, "customer_name", None)
        or name
    )
    _add_cbc(contact, "Name", contact_name)
    _add_cbc(contact, "Telephone", getattr(entity, "phone_no", "") or "")
    _add_cbc(contact, "ElectronicMail", getattr(entity, "email_id", "") or "")
    # Strip empty contact element if no children.
    if len(contact) == 0:
        party.remove(contact)


def _build_payment_means(invoice, iban: str, bic: str | None, factuur) -> None:
    """Add PaymentMeans block — required by Peppol BIS 3.0 receivers."""
    pm = etree.SubElement(invoice, _cac("PaymentMeans"))
    _add_cbc_required(pm, "PaymentMeansCode", "30")  # Credit transfer
    if factuur.factuurnummer:
        _add_cbc(pm, "PaymentID", factuur.factuurnummer)

    payee = etree.SubElement(pm, _cac("PayeeFinancialAccount"))
    _add_cbc_required(payee, "ID", iban.replace(" ", "").upper())
    if bic:
        branch = etree.SubElement(payee, _cac("FinancialInstitutionBranch"))
        _add_cbc_required(branch, "ID", bic)


def _build_tax_total(invoice, factuur) -> None:
    btw_bedrag = flt(factuur.btw_bedrag or 0, 2)
    excl = flt(factuur.bedrag_excl_btw or 0, 2)
    pct = flt(factuur.btw_percentage or 0, 2)

    tax_total = etree.SubElement(invoice, _cac("TaxTotal"))
    _add_cbc_required(tax_total, "TaxAmount", f"{btw_bedrag:.2f}", currencyID="EUR")

    subtotal = etree.SubElement(tax_total, _cac("TaxSubtotal"))
    _add_cbc_required(subtotal, "TaxableAmount", f"{excl:.2f}", currencyID="EUR")
    _add_cbc_required(subtotal, "TaxAmount", f"{btw_bedrag:.2f}", currencyID="EUR")

    tax_cat = etree.SubElement(subtotal, _cac("TaxCategory"))
    # 'S' = Standard rated, 'AE' = Reverse charge, 'Z' = Zero rated, 'E' = Exempt.
    # We default to 'S'; refine when BTW reverse-charge / exemption lands.
    _add_cbc_required(tax_cat, "ID", "S")
    _add_cbc_required(tax_cat, "Percent", f"{pct:.2f}")

    scheme = etree.SubElement(tax_cat, _cac("TaxScheme"))
    _add_cbc_required(scheme, "ID", "VAT")


def _build_monetary_total(invoice, factuur) -> None:
    excl = flt(factuur.bedrag_excl_btw or 0, 2)
    incl = flt(factuur.bedrag_incl_btw or 0, 2)
    paid = flt(factuur.betaald_bedrag or 0, 2)
    payable = flt(incl - paid, 2)

    total = etree.SubElement(invoice, _cac("LegalMonetaryTotal"))
    _add_cbc_required(total, "LineExtensionAmount", f"{excl:.2f}", currencyID="EUR")
    _add_cbc_required(total, "TaxExclusiveAmount", f"{excl:.2f}", currencyID="EUR")
    _add_cbc_required(total, "TaxInclusiveAmount", f"{incl:.2f}", currencyID="EUR")
    if paid > 0:
        _add_cbc_required(total, "PrepaidAmount", f"{paid:.2f}", currencyID="EUR")
    _add_cbc_required(total, "PayableAmount", f"{payable:.2f}", currencyID="EUR")


def _build_invoice_line(invoice, factuur) -> None:
    """Single invoice line for the full amount (current model has no line items)."""
    excl = flt(factuur.bedrag_excl_btw or 0, 2)
    pct = flt(factuur.btw_percentage or 0, 2)

    line = etree.SubElement(invoice, _cac("InvoiceLine"))
    _add_cbc_required(line, "ID", "1")
    _add_cbc_required(line, "InvoicedQuantity", "1", unitCode="EA")
    _add_cbc_required(line, "LineExtensionAmount", f"{excl:.2f}", currencyID="EUR")

    item = etree.SubElement(line, _cac("Item"))
    _add_cbc_required(
        item,
        "Name",
        factuur.referentie or f"Factuur {factuur.factuurnummer or factuur.name}",
    )
    if factuur.opmerkingen:
        _add_cbc(item, "Description", factuur.opmerkingen)

    item_tax = etree.SubElement(item, _cac("ClassifiedTaxCategory"))
    _add_cbc_required(item_tax, "ID", "S")
    _add_cbc_required(item_tax, "Percent", f"{pct:.2f}")
    scheme = etree.SubElement(item_tax, _cac("TaxScheme"))
    _add_cbc_required(scheme, "ID", "VAT")

    price = etree.SubElement(line, _cac("Price"))
    _add_cbc_required(price, "PriceAmount", f"{excl:.2f}", currencyID="EUR")


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
