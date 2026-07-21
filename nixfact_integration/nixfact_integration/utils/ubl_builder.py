# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""UBL 2.1 / Peppol BIS 3.0 XML-builder.

Puur: neemt een UBLFactuur en geeft XML terug. Geen frappe, geen IO.
"""

from __future__ import annotations

import re

from lxml import etree

from nixfact_integration.utils.btw import NUL_CATEGORIEEN, VRIJSTELLING_REDEN
from nixfact_integration.utils.ubl_model import UBLFactuur, UBLPartij, UBLRegel

# UBL 2.1 namespaces.
NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

NSMAP = {None: NS_INVOICE, "cac": NS_CAC, "cbc": NS_CBC}

# Peppol BIS 3.0 identifiers.
CUSTOMIZATION_ID = (
    "urn:cen.eu:en16931:2017"
    "#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
)
PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"

VALUTA = "EUR"

# Strip XML 1.0 illegal control chars (alles < 0x20 behalve TAB/LF/CR).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _cac(tag: str) -> str:
    return f"{{{NS_CAC}}}{tag}"


def _cbc(tag: str) -> str:
    return f"{{{NS_CBC}}}{tag}"


def _xml_safe(value: object) -> str:
    if value is None:
        return ""
    return _CONTROL_CHARS_RE.sub("", str(value))


def _add_cbc(parent, tag: str, text, **attribs):
    """Voeg een CBC-element toe; slaat lege waarden over."""
    safe = _xml_safe(text)
    if not safe:
        return None
    el = etree.SubElement(parent, _cbc(tag), **attribs)
    el.text = safe
    return el


def _add_cbc_required(parent, tag: str, text, **attribs):
    """Voeg een CBC-element toe, ook als het leeg is."""
    el = etree.SubElement(parent, _cbc(tag), **attribs)
    el.text = _xml_safe(text)
    return el


def _bedrag(waarde: float) -> str:
    return f"{float(waarde):.2f}"


def _aantal(waarde: float) -> str:
    """Formatteer aantallen zonder onnodige decimalen (8.0 -> '8')."""
    getal = float(waarde)
    return str(int(getal)) if getal == int(getal) else f"{getal:.2f}"


def build_invoice_xml(factuur: UBLFactuur) -> str:
    """Bouw de volledige Invoice-XML voor een UBLFactuur."""
    invoice = etree.Element("Invoice", nsmap=NSMAP)

    _add_cbc(invoice, "CustomizationID", CUSTOMIZATION_ID)
    _add_cbc(invoice, "ProfileID", PROFILE_ID)
    _add_cbc_required(invoice, "ID", factuur.nummer)
    _add_cbc_required(invoice, "IssueDate", factuur.factuurdatum)
    if factuur.vervaldatum:
        _add_cbc(invoice, "DueDate", factuur.vervaldatum)
    _add_cbc(invoice, "InvoiceTypeCode", "380")
    _add_cbc(invoice, "DocumentCurrencyCode", VALUTA)
    if factuur.referentie:
        _add_cbc(invoice, "BuyerReference", factuur.referentie)

    leverancier = etree.SubElement(invoice, _cac("AccountingSupplierParty"))
    _build_party(leverancier, factuur.leverancier)

    afnemer = etree.SubElement(invoice, _cac("AccountingCustomerParty"))
    _build_party(afnemer, factuur.afnemer)

    if factuur.iban:
        _build_payment_means(invoice, factuur)

    _build_tax_total(invoice, factuur)
    _build_monetary_total(invoice, factuur)

    for index, regel in enumerate(factuur.regels, start=1):
        _build_invoice_line(invoice, index, regel)

    return etree.tostring(
        invoice, pretty_print=True, xml_declaration=True, encoding="UTF-8"
    ).decode("utf-8")


def _build_party(parent_element, partij: UBLPartij) -> None:
    """Bouw een Party-blok met de Peppol BIS 3.0 verplichte onderdelen."""
    party = etree.SubElement(parent_element, _cac("Party"))

    btw = (partij.btw_nummer or "").strip()
    if btw:
        endpoint = etree.SubElement(party, _cbc("EndpointID"), schemeID="9944")
        endpoint.text = _xml_safe(btw)

    naam_el = etree.SubElement(party, _cac("PartyName"))
    _add_cbc_required(naam_el, "Name", partij.naam)

    postal = etree.SubElement(party, _cac("PostalAddress"))
    _add_cbc(postal, "StreetName", partij.straat)
    _add_cbc(postal, "AdditionalStreetName", partij.extra_straat)
    _add_cbc(postal, "CityName", partij.plaats)
    _add_cbc(postal, "PostalZone", partij.postcode)
    land = etree.SubElement(postal, _cac("Country"))
    _add_cbc_required(
        land,
        "IdentificationCode",
        (partij.landcode or "NL").upper(),
        listID="ISO3166-1:Alpha2",
    )

    if btw:
        tax_scheme_el = etree.SubElement(party, _cac("PartyTaxScheme"))
        _add_cbc_required(tax_scheme_el, "CompanyID", btw)
        scheme = etree.SubElement(tax_scheme_el, _cac("TaxScheme"))
        _add_cbc_required(scheme, "ID", "VAT")

    legal = etree.SubElement(party, _cac("PartyLegalEntity"))
    _add_cbc_required(legal, "RegistrationName", partij.naam)
    if btw:
        _add_cbc(legal, "CompanyID", btw)

    contact = etree.SubElement(party, _cac("Contact"))
    _add_cbc(contact, "Name", partij.naam)
    _add_cbc(contact, "Telephone", partij.telefoon)
    _add_cbc(contact, "ElectronicMail", partij.email)
    if len(contact) == 0:
        party.remove(contact)


def _build_payment_means(invoice, factuur: UBLFactuur) -> None:
    pm = etree.SubElement(invoice, _cac("PaymentMeans"))
    _add_cbc_required(pm, "PaymentMeansCode", "30")  # Credit transfer
    if factuur.nummer:
        _add_cbc(pm, "PaymentID", factuur.nummer)

    payee = etree.SubElement(pm, _cac("PayeeFinancialAccount"))
    _add_cbc_required(payee, "ID", factuur.iban.replace(" ", "").upper())
    if factuur.bic:
        branch = etree.SubElement(payee, _cac("FinancialInstitutionBranch"))
        _add_cbc_required(branch, "ID", factuur.bic)


def _build_tax_total(invoice, factuur: UBLFactuur) -> None:
    """Eén TaxSubtotal per btw-groep — vereist door BR-CO-18."""
    groepen = factuur.btw_groepen()
    som = factuur.totalen()

    tax_total = etree.SubElement(invoice, _cac("TaxTotal"))
    _add_cbc_required(
        tax_total, "TaxAmount", _bedrag(som["btw"]), currencyID=VALUTA
    )

    for groep in groepen:
        subtotal = etree.SubElement(tax_total, _cac("TaxSubtotal"))
        _add_cbc_required(
            subtotal, "TaxableAmount", _bedrag(groep.excl), currencyID=VALUTA
        )
        _add_cbc_required(
            subtotal, "TaxAmount", _bedrag(groep.btw), currencyID=VALUTA
        )

        categorie = etree.SubElement(subtotal, _cac("TaxCategory"))
        _add_cbc_required(categorie, "ID", groep.code)
        _add_cbc_required(categorie, "Percent", f"{groep.percentage:.2f}")
        if groep.code in NUL_CATEGORIEEN:
            _add_cbc(
                categorie,
                "TaxExemptionReason",
                VRIJSTELLING_REDEN.get(groep.code, ""),
            )
        scheme = etree.SubElement(categorie, _cac("TaxScheme"))
        _add_cbc_required(scheme, "ID", "VAT")


def _build_monetary_total(invoice, factuur: UBLFactuur) -> None:
    som = factuur.totalen()
    betaald = float(factuur.betaald_bedrag or 0)
    te_betalen = som["incl"] - betaald

    total = etree.SubElement(invoice, _cac("LegalMonetaryTotal"))
    _add_cbc_required(
        total, "LineExtensionAmount", _bedrag(som["excl"]), currencyID=VALUTA
    )
    _add_cbc_required(
        total, "TaxExclusiveAmount", _bedrag(som["excl"]), currencyID=VALUTA
    )
    _add_cbc_required(
        total, "TaxInclusiveAmount", _bedrag(som["incl"]), currencyID=VALUTA
    )
    if betaald > 0:
        _add_cbc_required(
            total, "PrepaidAmount", _bedrag(betaald), currencyID=VALUTA
        )
    _add_cbc_required(
        total, "PayableAmount", _bedrag(te_betalen), currencyID=VALUTA
    )


def _build_invoice_line(invoice, index: int, regel: UBLRegel) -> None:
    line = etree.SubElement(invoice, _cac("InvoiceLine"))
    _add_cbc_required(line, "ID", str(index))
    _add_cbc_required(
        line, "InvoicedQuantity", _aantal(regel.aantal), unitCode="EA"
    )
    _add_cbc_required(
        line, "LineExtensionAmount", _bedrag(regel.excl), currencyID=VALUTA
    )

    item = etree.SubElement(line, _cac("Item"))
    _add_cbc_required(item, "Name", regel.omschrijving)

    item_tax = etree.SubElement(item, _cac("ClassifiedTaxCategory"))
    _add_cbc_required(item_tax, "ID", regel.btw_code)
    _add_cbc_required(item_tax, "Percent", f"{regel.btw_percentage:.2f}")
    scheme = etree.SubElement(item_tax, _cac("TaxScheme"))
    _add_cbc_required(scheme, "ID", "VAT")

    price = etree.SubElement(line, _cac("Price"))
    _add_cbc_required(
        price, "PriceAmount", _bedrag(regel.eenheidsprijs), currencyID=VALUTA
    )
