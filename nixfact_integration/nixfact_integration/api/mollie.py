# Copyright (c) 2026, Nick Aldewereld
# License: MIT

import frappe
from frappe import _


@frappe.whitelist()
def create_payment_link(factuur_name):
	"""
	Create a Mollie payment link for an invoice.

	Args:
	    factuur_name: NixFact Factuur document name

	Returns:
	    dict: {payment_url, payment_id}
	"""
	factuur = frappe.get_doc("NixFact Factuur", factuur_name)

	if factuur.status == "Betaald":
		frappe.throw(_("Deze factuur is al betaald."))

	if factuur.mollie_payment_id:
		# Check existing payment status first
		from nixfact_integration.integrations.mollie import MollieIntegration

		mollie = MollieIntegration()
		existing = mollie.get_payment(factuur.mollie_payment_id)
		if existing.get("status") in ("open", "pending"):
			return {
				"payment_url": factuur.mollie_payment_url,
				"payment_id": factuur.mollie_payment_id,
				"message": "Bestaande betaallink is nog actief.",
			}

	from nixfact_integration.integrations.mollie import MollieIntegration

	mollie = MollieIntegration()
	checkout_url = mollie.create_payment(factuur)

	return {
		"payment_url": checkout_url,
		"payment_id": factuur.mollie_payment_id,
	}
