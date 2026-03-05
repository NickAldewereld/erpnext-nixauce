# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Mollie payment integration for NIXFact invoices."""

import re

import frappe
import requests
from frappe import _
from frappe.utils import nowdate, get_url

# Mollie payment ID format: tr_ followed by alphanumeric
PAYMENT_ID_PATTERN = re.compile(r"^tr_[a-zA-Z0-9]+$")


class MollieIntegration:
	"""Client for the Mollie v2 payments API."""

	BASE_URL = "https://api.mollie.com/v2"

	def __init__(self, api_key=None):
		if api_key:
			self.api_key = api_key
		else:
			settings = frappe.get_single("NixFact Instellingen")
			if not settings.mollie_enabled:
				frappe.throw(_("Mollie is niet ingeschakeld in de instellingen."))
			self.api_key = settings.get_password("mollie_api_key")

		if not self.api_key:
			frappe.throw(_("Mollie API key is niet geconfigureerd."))

	def _headers(self):
		return {
			"Authorization": f"Bearer {self.api_key}",
			"Content-Type": "application/json",
		}

	def create_payment(self, factuur):
		"""Create a Mollie payment and store the checkout URL on the invoice."""
		if isinstance(factuur, str):
			factuur = frappe.get_doc("NixFact Factuur", factuur)

		if not factuur.bedrag_incl_btw or factuur.bedrag_incl_btw <= 0:
			frappe.throw(_("Factuurbedrag moet groter zijn dan 0."))

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
				message=f"Status {response.status_code}: {response.text[:500]}",
			)
			frappe.throw(_("Mollie API fout: {0}").format(response.status_code))

		data = response.json()
		payment_id = data["id"]
		checkout_url = data["_links"]["checkout"]["href"]

		factuur.mollie_payment_id = payment_id
		factuur.mollie_payment_url = checkout_url
		factuur.betaallink = checkout_url
		factuur.save(ignore_permissions=True)
		frappe.db.commit()

		return checkout_url

	def get_payment(self, payment_id):
		"""Fetch payment status from Mollie. Returns the payment data dict."""
		if not PAYMENT_ID_PATTERN.match(payment_id):
			frappe.throw(_("Ongeldig Mollie payment ID."))

		response = requests.get(
			f"{self.BASE_URL}/payments/{payment_id}",
			headers=self._headers(),
			timeout=30,
		)

		if response.status_code != 200:
			frappe.log_error(
				title="Mollie payment ophalen mislukt",
				message=f"Status {response.status_code}: {response.text[:500]}",
			)
			frappe.throw(_("Mollie API fout: {0}").format(response.status_code))

		return response.json()


@frappe.whitelist(allow_guest=True)
def webhook():
	"""Handle Mollie payment webhook. Guest-accessible as required by Mollie.

	Security: We never trust the webhook payload directly. The payment ID is
	validated against a known pattern, then the actual status is verified by
	calling the Mollie API before making any changes.
	"""
	payment_id = frappe.form_dict.get("id")
	if not payment_id or not PAYMENT_ID_PATTERN.match(str(payment_id)):
		return "OK"

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

	# Always verify with Mollie — never trust the webhook body alone
	try:
		mollie = MollieIntegration()
		payment_data = mollie.get_payment(payment_id)
	except Exception:
		frappe.log_error(
			title="Mollie webhook: status ophalen mislukt",
			message=frappe.get_traceback(),
		)
		return "OK"

	if payment_data.get("status") == "paid":
		factuur = frappe.get_doc("NixFact Factuur", factuur_name)
		factuur.status = "Betaald"
		factuur.betaald_bedrag = factuur.bedrag_incl_btw
		factuur.betaaldatum = nowdate()
		factuur.openstaand_bedrag = 0
		factuur.save(ignore_permissions=True)
		frappe.db.commit()

	return "OK"
