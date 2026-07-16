# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""NixFact Instellingen — global settings singleton."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

MIN_DAYS = 1


class NixFactInstellingen(Document):

    def validate(self) -> None:
        self._validate_termijnen()

    def _validate_termijnen(self) -> None:
        """All day-based settings must be a positive integer."""
        checks = [
            ("betalingstermijn_facturen", _("Betalingstermijn facturen moet minimaal 1 dag zijn.")),
            ("betalingstermijn_herinnering", _("Betalingstermijn herinnering moet minimaal 1 dag zijn.")),
            ("betalingstermijn_aanmaning", _("Betalingstermijn aanmaning moet minimaal 1 dag zijn.")),
            ("geldigheid_offertes", _("Geldigheid offertes moet minimaal 1 dag zijn.")),
            ("abonnement_vooraf_dagen", _("Abonnement-vooraf-dagen moet 0 of meer zijn.")),
            ("aantal_herinneringen", _("Aantal herinneringen moet minimaal 1 zijn.")),
        ]
        for field, msg in checks:
            value = getattr(self, field, None)
            if value is None:
                continue
            try:
                v = int(value)
            except (TypeError, ValueError):
                frappe.throw(msg)
            min_value = 0 if field == "abonnement_vooraf_dagen" else MIN_DAYS
            if v < min_value:
                frappe.throw(msg)
