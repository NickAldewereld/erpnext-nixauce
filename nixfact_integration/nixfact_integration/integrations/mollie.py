# Copyright (c) 2026, Nick Aldewereld
# License: MIT

import frappe
import requests
from frappe.utils import nowdate, get_url


class MollieIntegration:
	"""Integration with Mollie payment API."""

	BASE_URL = "https://api.mollie.com/v2"

	def __init__(self, api_key=None):
		"""
		Initialize with API key from settings or explicit key.

		Args:
		    api_key: Mollie API key. If None, reads from NixFactInstellingen.
		"""
		if api_key:
			self.api_key = api_key
		else:
			settings = frappe.get_single("NixFact Instellingen")
			if not settings.mollie_enabled:
				frappe.throw("Mollie is niet ingeschakeld in de instellingen.")
			self.api_key = settings.get_password("mollie_api_key")

		if not self.api_key:
			frappe.throw("Mollie API key is niet geconfigureerd.")

	def _headers(self):
		return {
			"Authorization": f"Bearer {self.api_key}",
			"Content-Type": "application/json",
		}

	def create_payment(self, factuur):
		"""
		Create a Mollie payment for an invoice.

		Args:
		    factuur: NixFact Factuur document name or Document

		Returns:
		    str: Checkout URL for the customer
		"""
		if isinstance(factuur, str):
			factuur = frappe.get_doc("NixFact Factuur", factuur)

		if not factuur.bedrag_incl_btw or factuur.bedrag_incl_btw <= 0:
			frappe.throw("Factuurbedrag moet groter zijn dan 0.")

		site_url = get_url()
		response = requests.post(
			f"{self.BASE_URL}/payments",
			json={
				"amount": {
					"currency": "EUR",
					"value": f"{factuur.bedrag_incl_btw:.2f}",
				},
				"description": f"Factuur {factuur.factuurnummer}",
				"redirectUrl": f"{site_url}/payment-success?factuur={factuur.name}",
				"webhookUrl": f"{site_url}/api/method/nixfact_integration.integrations.mollie.webhook",
				"metadata": {
					"factuur_name": factuur.name,
					"factuurnummer": factuur.factuurnummer,
				},
			},
			headers=self._headers(),
			timeout=30,
		)

		if response.status_code not in (200, 201):
			frappe.log_error(
				title="Mollie payment aanmaken mislukt",
				message=f"Status {response.status_code}: {response.text}",
			)
			frappe.throw(f"Mollie API fout: {response.status_code}")

		data = response.json()
		payment_id = data["id"]
		checkout_url = data["_links"]["checkout"]["href"]

		# Store payment info on the invoice
		factuur.mollie_payment_id = payment_id
		factuur.mollie_payment_url = checkout_url
		factuur.betaallink = checkout_url
		factuur.save(ignore_permissions=True)
		frappe.db.commit()

		return checkout_url

	def get_payment(self, payment_id):
		"""
		Get payment status from Mollie.

		Args:
		    payment_id: Mollie payment ID (e.g. tr_xxx)

		Returns:
		    dict: Payment data from Mollie
		"""
		response = requests.get(
			f"{self.BASE_URL}/payments/{payment_id}",
			headers=self._headers(),
			timeout=30,
		)

		if response.status_code != 200:
			frappe.log_error(
				title="Mollie payment ophalen mislukt",
				message=f"Status {response.status_code}: {response.text}",
			)
			frappe.throw(f"Mollie API fout: {response.status_code}")

		return response.json()


@frappe.whitelist(allow_guest=True)
def webhook():
	"""
	Handle Mollie payment webhook callbacks.

	Mollie sends a POST with payment ID when status changes.
	We verify the status and mark the invoice as paid if applicable.
	"""
	payment_id = frappe.form_dict.get("id")
	if not payment_id:
		frappe.throw("Geen payment ID ontvangen.")

	# Find the invoice linked to this payment
	factuur_name = frappe.db.get_value(
		"NixFact Factuur",
		{"mollie_payment_id": payment_id},
		"name",
	)

	if not factuur_name:
		frappe.log_error(
			title="Mollie webhook: factuur niet gevonden",
			message=f"Payment ID: {payment_id}",
		)
		return "OK"

	# Verify payment status with Mollie
	try:
		mollie = MollieIntegration()
		payment_data = mollie.get_payment(payment_id)
	except Exception:
		frappe.log_error(
			title="Mollie webhook: status ophalen mislukt",
			message=f"Payment ID: {payment_id}",
		)
		return "OK"

	status = payment_data.get("status")

	if status == "paid":
		factuur = frappe.get_doc("NixFact Factuur", factuur_name)
		factuur.status = "Betaald"
		factuur.betaald_bedrag = factuur.bedrag_incl_btw
		factuur.betaaldatum = nowdate()
		factuur.openstaand_bedrag = 0
		factuur.save(ignore_permissions=True)
		frappe.db.commit()

	return "OK"
