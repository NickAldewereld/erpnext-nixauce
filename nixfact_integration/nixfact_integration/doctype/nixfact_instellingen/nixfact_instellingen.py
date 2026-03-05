# Copyright (c) 2026, Nick Aldewereld
# License: MIT

from frappe.model.document import Document


class NixFactInstellingen(Document):

	def validate(self):
		if self.betalingstermijn_facturen and self.betalingstermijn_facturen < 1:
			from frappe import throw

			throw("Betalingstermijn facturen moet minimaal 1 dag zijn.")

		if self.betalingstermijn_herinnering and self.betalingstermijn_herinnering < 1:
			from frappe import throw

			throw("Betalingstermijn herinnering moet minimaal 1 dag zijn.")

		if self.geldigheid_offertes and self.geldigheid_offertes < 1:
			from frappe import throw

			throw("Geldigheid offertes moet minimaal 1 dag zijn.")
