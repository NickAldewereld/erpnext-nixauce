# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

import frappe
from frappe import _


@frappe.whitelist()
def generate_ubl_xml(factuur_name):
	"""
	Generate UBL 2.1 XML for an invoice and return it.

	Args:
	    factuur_name: NixFact Factuur document name

	Returns:
	    dict: {xml: str, factuurnummer: str}
	"""
	from nixfact_integration.utils.ubl_generator import generate_ubl_invoice

	xml = generate_ubl_invoice(factuur_name)
	factuur = frappe.get_doc("NixFact Factuur", factuur_name)

	return {
		"xml": xml,
		"factuurnummer": factuur.factuurnummer,
	}


@frappe.whitelist()
def attach_ubl_to_factuur(factuur_name):
	"""
	Generate UBL XML, attach it to the invoice, and return the file URL.

	Args:
	    factuur_name: NixFact Factuur document name

	Returns:
	    dict: {file_url: str, factuurnummer: str}
	"""
	from nixfact_integration.utils.ubl_generator import generate_and_attach_ubl

	file_url = generate_and_attach_ubl(factuur_name)
	factuur = frappe.get_doc("NixFact Factuur", factuur_name)

	return {
		"file_url": file_url,
		"factuurnummer": factuur.factuurnummer,
	}
