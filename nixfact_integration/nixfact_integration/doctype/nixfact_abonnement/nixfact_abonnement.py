# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class NixFactAbonnement(Document):

    def validate(self) -> None:
        self.bereken_bedragen()
        self._validate_dates()

    def bereken_bedragen(self) -> None:
        if self.bedrag_excl_btw:
            excl = flt(self.bedrag_excl_btw, 2)
            pct = flt(self.btw_percentage or 0, 2)
            self.bedrag_excl_btw = excl
            self.bedrag_incl_btw = flt(excl + (excl * pct / 100), 2)

    def _validate_dates(self) -> None:
        if self.einddatum and self.startdatum and getdate(self.einddatum) < getdate(self.startdatum):
            frappe.throw(_("Einddatum mag niet vóór startdatum liggen."))
        if (
            self.volgende_factuur_datum
            and self.startdatum
            and getdate(self.volgende_factuur_datum) < getdate(self.startdatum)
        ):
            frappe.throw(_("Volgende factuurdatum mag niet vóór startdatum liggen."))
