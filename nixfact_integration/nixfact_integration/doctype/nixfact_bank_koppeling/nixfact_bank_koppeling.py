# Copyright (c) 2026, Nick Aldewereld
# License: MIT

import frappe
from frappe.model.document import Document


class NixFactBankKoppeling(Document):

	def validate(self):
		if self.koppeling_type == "Ponto" and self.actief:
			if not self.ponto_client_id or not self.ponto_client_secret:
				frappe.throw("Ponto Client ID en Client Secret zijn verplicht.")
			if not self.account_id:
				frappe.throw("Account ID is verplicht voor Ponto koppeling.")
