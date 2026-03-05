# Copyright (c) 2026, Nick Aldewereld
# License: MIT

from frappe.model.document import Document

from nixfact_integration.utils.numbering import set_nummer_for_doc


class NixFactOfferte(Document):

	def autoname(self):
		set_nummer_for_doc(self, "NixFact Offerte")
