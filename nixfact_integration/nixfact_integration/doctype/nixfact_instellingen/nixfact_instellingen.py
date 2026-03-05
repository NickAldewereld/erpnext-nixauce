# Copyright (c) 2026, Nick Aldewereld
# License: MIT

"""NixFact Instellingen — global settings singleton."""

import frappe
from frappe import _
from frappe.model.document import Document

MIN_DAYS = 1


class NixFactInstellingen(Document):

	def validate(self):
		self._validate_termijnen()

	def _validate_termijnen(self):
		"""Ensure all day-based settings are at least 1."""
		checks = [
			("betalingstermijn_facturen", _("Betalingstermijn facturen moet minimaal 1 dag zijn.")),
			("betalingstermijn_herinnering", _("Betalingstermijn herinnering moet minimaal 1 dag zijn.")),
			("betalingstermijn_aanmaning", _("Betalingstermijn aanmaning moet minimaal 1 dag zijn.")),
			("geldigheid_offertes", _("Geldigheid offertes moet minimaal 1 dag zijn.")),
		]
		for field, msg in checks:
			value = getattr(self, field, None)
			if value is not None and value < MIN_DAYS:
				frappe.throw(msg)
