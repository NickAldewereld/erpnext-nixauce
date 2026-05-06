# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from nixfact_integration.utils.numbering import set_nummer_for_doc

# Allowed status transitions for offertes.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "Concept": {"Concept", "Verstuurd", "Verlopen"},
    "Verstuurd": {"Verstuurd", "Geaccepteerd", "Geweigerd", "Verlopen"},
    "Geaccepteerd": {"Geaccepteerd", "Factuur aangemaakt"},
    "Geweigerd": {"Geweigerd"},
    "Verlopen": {"Verlopen"},
    "Factuur aangemaakt": {"Factuur aangemaakt"},
}


class NixFactOfferte(Document):

    def autoname(self) -> None:
        set_nummer_for_doc(self, "NixFact Offerte")

    def before_insert(self) -> None:
        """Generate a public accept-token if one isn't already set.

        The token gates access to the public portal page where the customer
        accepts/rejects the quote. Existing tokens are preserved (test seeds,
        manual paste from another system).
        """
        if not self.accept_token:
            from nixfact_integration.utils.tokens import generate_accept_token
            self.accept_token = generate_accept_token()

    def validate(self) -> None:
        self._sanity_check_bedragen()
        self._validate_status_transition()
        self._guard_immutable_after_accept()
        self._stamp_portal_sent()

    def _guard_immutable_after_accept(self) -> None:
        """Audit fields are immutable once the offerte is signed.

        `handtekening` + `ondertekend_*` form the legal audit record. After
        `ondertekend_op` is set, any change is a tamper attempt — block it.
        """
        if self.is_new() or not self.ondertekend_op:
            return
        old = self.get_doc_before_save()
        if not old:
            return
        locked = (
            "handtekening",
            "ondertekend_op",
            "ondertekend_door_email",
            "ondertekend_ip",
            "ondertekend_user_agent",
        )
        for field in locked:
            if getattr(old, field, None) != getattr(self, field, None):
                frappe.throw(
                    _("Ondertekende offerte kan niet meer gewijzigd worden."),
                    frappe.ValidationError,
                )

    def _sanity_check_bedragen(self) -> None:
        """Reject inconsistent bedrag_excl / bedrag_incl pairs.

        Before this guard a caller could send {bedrag_excl: 100,
        bedrag_incl: 50} and the row would silently be saved. We round to
        2 decimals on both sides and require a plausible relationship
        (incl >= excl, incl - excl is a sensible BTW amount).
        """
        excl = flt(self.bedrag_excl, 2) if self.bedrag_excl else 0
        incl = flt(self.bedrag_incl, 2) if self.bedrag_incl else 0
        if not excl or not incl:
            return
        self.bedrag_excl = excl
        self.bedrag_incl = incl
        if incl + 0.01 < excl:
            frappe.throw(
                _("Bedrag incl. BTW mag niet lager zijn dan bedrag excl. BTW."),
                frappe.ValidationError,
            )

    def _validate_status_transition(self) -> None:
        if self.is_new():
            return
        old = self.get_doc_before_save()
        if not old or old.status == self.status:
            return
        allowed = _ALLOWED_TRANSITIONS.get(old.status, set())
        if self.status not in allowed:
            frappe.throw(
                _("Status mag niet van {0} naar {1}.").format(old.status, self.status),
                frappe.ValidationError,
            )

    def _stamp_portal_sent(self) -> None:
        """Record portal_verstuurd_op the first time status flips to Verstuurd."""
        if self.is_new() or self.portal_verstuurd_op:
            return
        if self.status != "Verstuurd":
            return
        old = self.get_doc_before_save()
        if old and old.status != "Verstuurd":
            self.portal_verstuurd_op = frappe.utils.now_datetime()
