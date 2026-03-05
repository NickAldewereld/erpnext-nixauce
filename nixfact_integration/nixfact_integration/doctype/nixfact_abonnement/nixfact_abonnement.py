# Copyright (c) 2026, Nick Aldewereld
# License: MIT

from frappe.model.document import Document


class NixFactAbonnement(Document):

	def validate(self):
		self.bereken_bedragen()

	def bereken_bedragen(self):
		if self.bedrag_excl_btw:
			btw_pct = (self.btw_percentage or 0) / 100
			self.bedrag_incl_btw = self.bedrag_excl_btw + (self.bedrag_excl_btw * btw_pct)
