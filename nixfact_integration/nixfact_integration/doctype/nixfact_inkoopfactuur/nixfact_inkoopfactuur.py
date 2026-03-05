# Copyright (c) 2026, Nick Aldewereld
# License: MIT

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime

from nixfact_integration.utils.numbering import set_nummer_for_doc


class NixFactInkoopfactuur(Document):

	def autoname(self):
		set_nummer_for_doc(self, "NixFact Inkoopfactuur")

	def validate(self):
		self.bereken_bedragen()

	def on_update(self):
		if self.status == "Geboekt" and not self.verwerkt_op:
			self.db_set("verwerkt_op", get_datetime())

	def bereken_bedragen(self):
		if self.bedrag_excl:
			btw_pct = (self.btw_percentage or 0) / 100
			self.btw_bedrag = self.bedrag_excl * btw_pct
			self.bedrag_incl = self.bedrag_excl + self.btw_bedrag
