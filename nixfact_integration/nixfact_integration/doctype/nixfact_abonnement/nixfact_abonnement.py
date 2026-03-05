# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

from frappe.model.document import Document


class NixFactAbonnement(Document):

	def validate(self):
		self.bereken_bedragen()

	def bereken_bedragen(self):
		if self.bedrag_excl_btw:
			btw_pct = (self.btw_percentage or 0) / 100
			self.bedrag_incl_btw = self.bedrag_excl_btw + (self.bedrag_excl_btw * btw_pct)
