# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class NixFactBankKoppeling(Document):

    def validate(self) -> None:
        if self.koppeling_type == "Ponto" and self.actief:
            if not self.ponto_client_id or not self.ponto_client_secret:
                frappe.throw(
                    _("Ponto Client ID en Client Secret zijn verplicht.")
                )
            if not self.account_id:
                frappe.throw(_("Account ID is verplicht voor Ponto koppeling."))
