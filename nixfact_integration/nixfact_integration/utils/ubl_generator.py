# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

import frappe
from frappe.utils import nowdate
from lxml import etree


# UBL 2.1 Namespaces
NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

NSMAP = {
	None: NS_INVOICE,
	"cac": NS_CAC,
	"cbc": NS_CBC,
}


def generate_ubl_invoice(factuur_name):
	"""
	Generate a UBL 2.1 Invoice XML document for a NixFact Factuur.

	Args:
	    factuur_name: NixFact Factuur document name

	Returns:
	    str: UBL 2.1 XML string
	"""
	factuur = frappe.get_doc("NixFact Factuur", factuur_name)

	# Get supplier info from default company
	company_name = frappe.defaults.get_defaults().get("company")
	company = None
	if company_name:
		company = frappe.get_doc("Company", company_name)

	# Get customer info
	customer = frappe.get_doc("Customer", factuur.klant) if factuur.klant else None
	customer_address = _get_primary_address(factuur.klant, "Customer") if factuur.klant else {}

	# Build XML
	invoice = etree.Element("Invoice", nsmap=NSMAP)

	# Header
	_add_cbc(invoice, "UBLVersionID", "2.1")
	_add_cbc(invoice, "CustomizationID",
		"urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0")
	_add_cbc(invoice, "ProfileID", "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0")
	_add_cbc(invoice, "ID", factuur.factuurnummer or factuur.name)
	_add_cbc(invoice, "IssueDate", str(factuur.factuur_datum or nowdate()))
	if factuur.vervaldatum:
		_add_cbc(invoice, "DueDate", str(factuur.vervaldatum))
	_add_cbc(invoice, "InvoiceTypeCode", "380")
	_add_cbc(invoice, "DocumentCurrencyCode", "EUR")

	# Supplier party
	supplier_party = etree.SubElement(invoice, _cac("AccountingSupplierParty"))
	_build_party(supplier_party, company, _get_company_address(company_name))

	# Customer party
	customer_party = etree.SubElement(invoice, _cac("AccountingCustomerParty"))
	_build_party(customer_party, customer, customer_address)

	# Tax total
	_build_tax_total(invoice, factuur)

	# Legal monetary total
	_build_monetary_total(invoice, factuur)

	# Invoice line (single line for the full invoice amount)
	_build_invoice_line(invoice, factuur)

	return etree.tostring(
		invoice,
		pretty_print=True,
		xml_declaration=True,
		encoding="UTF-8",
	).decode("utf-8")


def generate_and_attach_ubl(factuur_name):
	"""
	Generate UBL XML and attach it to the invoice as a file.

	Args:
	    factuur_name: NixFact Factuur document name

	Returns:
	    str: URL of the attached file
	"""
	xml_content = generate_ubl_invoice(factuur_name)
	factuur = frappe.get_doc("NixFact Factuur", factuur_name)
	filename = f"{factuur.factuurnummer or factuur.name}.xml"

	file_doc = frappe.get_doc({
		"doctype": "File",
		"file_name": filename,
		"attached_to_doctype": "NixFact Factuur",
		"attached_to_name": factuur_name,
		"content": xml_content,
		"is_private": 1,
	})
	file_doc.save(ignore_permissions=True)
	frappe.db.commit()

	return file_doc.file_url


# --- XML builder helpers ---


def _cac(tag):
	"""Return fully qualified CAC tag name."""
	return f"{{{NS_CAC}}}{tag}"


def _cbc(tag):
	"""Return fully qualified CBC tag name."""
	return f"{{{NS_CBC}}}{tag}"


def _add_cbc(parent, tag, text, **attribs):
	"""Add a CBC element with text content."""
	el = etree.SubElement(parent, _cbc(tag), **attribs)
	el.text = str(text) if text is not None else ""
	return el


def _build_party(parent_element, entity, address):
	"""Build AccountingSupplierParty or AccountingCustomerParty."""
	party = etree.SubElement(parent_element, _cac("Party"))

	# Party name
	party_name_el = etree.SubElement(party, _cac("PartyName"))
	name = ""
	if entity:
		name = getattr(entity, "company_name", None) or getattr(entity, "customer_name", "") or ""
	_add_cbc(party_name_el, "Name", name)

	# Postal address
	postal = etree.SubElement(party, _cac("PostalAddress"))
	_add_cbc(postal, "StreetName", address.get("address_line1", ""))
	_add_cbc(postal, "CityName", address.get("city", ""))
	_add_cbc(postal, "PostalZone", address.get("pincode", ""))

	country_el = etree.SubElement(postal, _cac("Country"))
	_add_cbc(country_el, "IdentificationCode", address.get("country_code", "NL"))

	# Contact
	if entity:
		contact = etree.SubElement(party, _cac("Contact"))
		email = getattr(entity, "email_id", "") or ""
		phone = getattr(entity, "phone_no", "") or ""
		_add_cbc(contact, "ElectronicMail", email)
		if phone:
			_add_cbc(contact, "Telephone", phone)


def _build_tax_total(invoice, factuur):
	"""Build TaxTotal element."""
	tax_total = etree.SubElement(invoice, _cac("TaxTotal"))
	btw_bedrag = factuur.btw_bedrag or 0
	_add_cbc(tax_total, "TaxAmount", f"{btw_bedrag:.2f}", currencyID="EUR")

	# Tax subtotal
	subtotal = etree.SubElement(tax_total, _cac("TaxSubtotal"))
	_add_cbc(subtotal, "TaxableAmount", f"{factuur.bedrag_excl_btw or 0:.2f}", currencyID="EUR")
	_add_cbc(subtotal, "TaxAmount", f"{btw_bedrag:.2f}", currencyID="EUR")

	tax_cat = etree.SubElement(subtotal, _cac("TaxCategory"))
	_add_cbc(tax_cat, "ID", "S")
	_add_cbc(tax_cat, "Percent", f"{factuur.btw_percentage or 0:.0f}")

	tax_scheme = etree.SubElement(tax_cat, _cac("TaxScheme"))
	_add_cbc(tax_scheme, "ID", "VAT")


def _build_monetary_total(invoice, factuur):
	"""Build LegalMonetaryTotal element."""
	total = etree.SubElement(invoice, _cac("LegalMonetaryTotal"))
	excl = factuur.bedrag_excl_btw or 0
	incl = factuur.bedrag_incl_btw or 0

	_add_cbc(total, "LineExtensionAmount", f"{excl:.2f}", currencyID="EUR")
	_add_cbc(total, "TaxExclusiveAmount", f"{excl:.2f}", currencyID="EUR")
	_add_cbc(total, "TaxInclusiveAmount", f"{incl:.2f}", currencyID="EUR")
	_add_cbc(total, "PayableAmount", f"{incl:.2f}", currencyID="EUR")


def _build_invoice_line(invoice, factuur):
	"""Build InvoiceLine element."""
	line = etree.SubElement(invoice, _cac("InvoiceLine"))
	_add_cbc(line, "ID", "1")
	_add_cbc(line, "InvoicedQuantity", "1", unitCode="C62")
	_add_cbc(line, "LineExtensionAmount", f"{factuur.bedrag_excl_btw or 0:.2f}", currencyID="EUR")

	# Item
	item = etree.SubElement(line, _cac("Item"))
	_add_cbc(item, "Name", factuur.referentie or f"Factuur {factuur.factuurnummer}")
	_add_cbc(item, "Description", factuur.opmerkingen or "")

	# Item tax category
	item_tax = etree.SubElement(item, _cac("ClassifiedTaxCategory"))
	_add_cbc(item_tax, "ID", "S")
	_add_cbc(item_tax, "Percent", f"{factuur.btw_percentage or 0:.0f}")
	tax_scheme = etree.SubElement(item_tax, _cac("TaxScheme"))
	_add_cbc(tax_scheme, "ID", "VAT")

	# Price
	price = etree.SubElement(line, _cac("Price"))
	_add_cbc(price, "PriceAmount", f"{factuur.bedrag_excl_btw or 0:.2f}", currencyID="EUR")


# --- Address helpers ---


def _get_primary_address(party_name, party_type):
	"""Get the primary address for a customer or supplier."""
	address_name = frappe.db.get_value(
		"Dynamic Link",
		{"link_doctype": party_type, "link_name": party_name, "parenttype": "Address"},
		"parent",
	)
	if not address_name:
		return {}

	addr = frappe.get_doc("Address", address_name)
	country_code = "NL"
	if addr.country:
		country_code = frappe.db.get_value("Country", addr.country, "code") or "NL"

	return {
		"address_line1": addr.address_line1 or "",
		"city": addr.city or "",
		"pincode": addr.pincode or "",
		"country_code": country_code.upper(),
	}


def _get_company_address(company_name):
	"""Get address for the default company."""
	if not company_name:
		return {}
	return _get_primary_address(company_name, "Company")
