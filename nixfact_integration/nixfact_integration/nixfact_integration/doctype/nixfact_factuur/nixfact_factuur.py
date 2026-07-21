# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt

from nixfact_integration.utils.btw import code_voor_categorie, regel_excl, totalen
from nixfact_integration.utils.numbering import set_nummer_for_doc


def regels_als_dicts(doc) -> list[dict]:
    """Zet de regels van een factuur om naar rekendicts voor utils.btw.

    Schrijft en passant het regeltotaal terug op elke regel, zodat de
    gebruiker het in de grid ziet.
    """
    resultaat = []
    for regel in getattr(doc, "regels", None) or []:
        excl = regel_excl(regel.aantal, regel.eenheidsprijs)
        regel.regel_excl = excl
        resultaat.append(
            {
                "omschrijving": regel.omschrijving,
                "aantal": float(regel.aantal or 0),
                "eenheidsprijs": float(regel.eenheidsprijs or 0),
                "excl": excl,
                "btw_percentage": float(regel.btw_percentage or 0),
                "btw_code": code_voor_categorie(regel.btw_categorie),
            }
        )
    return resultaat


# Allowed status transitions. Anything not listed is blocked at validate time.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "Concept": {"Concept", "Verstuurd", "Oninbaar"},
    "Verstuurd": {"Verstuurd", "Betaald", "Herinnering verstuurd", "Oninbaar"},
    "Herinnering verstuurd": {
        "Herinnering verstuurd",
        "Betaald",
        "Aanmaning verstuurd",
        "Oninbaar",
    },
    "Aanmaning verstuurd": {"Aanmaning verstuurd", "Betaald", "Oninbaar"},
    "Betaald": {"Betaald"},  # terminal — credit-note flow needed to revert
    "Oninbaar": {"Oninbaar"},  # terminal
}


class NixFactFactuur(Document):

    def autoname(self) -> None:
        set_nummer_for_doc(self, "NixFact Factuur")

    def validate(self) -> None:
        self.bereken_bedragen()
        self.set_vervaldatum()
        self._validate_status_transition()

    def bereken_bedragen(self) -> None:
        """Compute BTW + totalen uit de regels, currency-safe."""
        regels = regels_als_dicts(self)
        som = totalen(regels)
        self.bedrag_excl_btw = som["excl"]
        self.btw_bedrag = som["btw"]
        self.bedrag_incl_btw = som["incl"]
        self.openstaand_bedrag = flt(
            som["incl"] - flt(self.betaald_bedrag or 0, 2), 2
        )
        # btw_percentage blijft als samenvatting staan: het hoogste
        # gehanteerde tarief. Puur informatief; UBL gebruikt de groepen.
        self.btw_percentage = max(
            (r["btw_percentage"] for r in regels), default=0
        )

    def set_vervaldatum(self) -> None:
        """Set due date from settings if not manually set."""
        if self.factuur_datum and not self.vervaldatum:
            settings = frappe.get_single("NixFact Instellingen")
            dagen = max(1, int(settings.betalingstermijn_facturen or 14))
            self.vervaldatum = add_days(self.factuur_datum, dagen)

    def _validate_status_transition(self) -> None:
        """Block illegal status transitions on saved docs."""
        if self.is_new():
            return
        old = self.get_doc_before_save()
        if not old:
            return
        old_status = old.status
        new_status = self.status
        if old_status == new_status:
            return
        allowed = _ALLOWED_TRANSITIONS.get(old_status, set())
        if new_status not in allowed:
            frappe.throw(
                _("Status mag niet van {0} naar {1}.").format(old_status, new_status),
                frappe.ValidationError,
            )
