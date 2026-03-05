# Copyright (c) 2026, Nick Aldewereld
# License: MIT

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, nowdate, getdate

from nixfact_integration.utils.numbering import set_nummer_for_doc


class NixFactFactuur(Document):

	def autoname(self):
		set_nummer_for_doc(self, "NixFact Factuur")

	def validate(self):
		self.bereken_bedragen()
		self.set_vervaldatum()

	def bereken_bedragen(self):
		"""Calculate BTW and totals."""
		if self.bedrag_excl_btw:
			btw_pct = (self.btw_percentage or 0) / 100
			self.btw_bedrag = self.bedrag_excl_btw * btw_pct
			self.bedrag_incl_btw = self.bedrag_excl_btw + self.btw_bedrag
			self.openstaand_bedrag = self.bedrag_incl_btw - (self.betaald_bedrag or 0)

	def set_vervaldatum(self):
		"""Set due date from settings if not manually set."""
		if self.factuur_datum and not self.vervaldatum:
			settings = frappe.get_single("NixFact Instellingen")
			dagen = settings.betalingstermijn_facturen or 14
			self.vervaldatum = add_days(self.factuur_datum, dagen)
