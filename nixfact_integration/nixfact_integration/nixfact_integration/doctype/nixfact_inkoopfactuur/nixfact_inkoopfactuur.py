# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

from __future__ import annotations

from frappe.model.document import Document
from frappe.utils import flt, get_datetime

from nixfact_integration.utils.numbering import set_nummer_for_doc


class NixFactInkoopfactuur(Document):

    def autoname(self) -> None:
        set_nummer_for_doc(self, "NixFact Inkoopfactuur")

    def validate(self) -> None:
        self.bereken_bedragen()

    def on_update(self) -> None:
        if self.status == "Geboekt" and not self.verwerkt_op:
            self.db_set("verwerkt_op", get_datetime())

    def bereken_bedragen(self) -> None:
        excl = flt(self.bedrag_excl, 2) if self.bedrag_excl else 0
        pct = flt(self.btw_percentage or 0, 2)
        self.bedrag_excl = excl
        self.btw_bedrag = flt(excl * pct / 100, 2)
        self.bedrag_incl = flt(excl + self.btw_bedrag, 2)
