# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

from frappe.model.document import Document

from nixfact_integration.utils.numbering import set_nummer_for_doc


class NixFactOfferte(Document):

	def autoname(self):
		set_nummer_for_doc(self, "NixFact Offerte")
