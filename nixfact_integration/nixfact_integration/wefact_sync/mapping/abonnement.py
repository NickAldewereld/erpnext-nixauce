# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-abonnement → NixFact-Abonnement-dict. Puur."""

from __future__ import annotations

from nixfact_integration.wefact_sync.mapping.invoice import strip_html

_FREQ = {"m": "Maandelijks", "k": "Kwartaal", "j": "Jaarlijks", "w": "Maandelijks"}


def wefact_frequentie(periodic: str) -> str:
    return _FREQ.get((periodic or "").strip().lower(), "Maandelijks")


def abonnement_to_dict(wf: dict) -> dict:
    return {
        "klant_debtor_code": (wf.get("DebtorCode") or "").strip(),
        "omschrijving": strip_html(wf.get("Description")),
        "bedrag_excl_btw": float(wf.get("PriceExcl") or 0),
        "btw_percentage": float(wf.get("TaxPercentage") or 0),
        "frequentie": wefact_frequentie(wf.get("Periodic")),
        "volgende_factuur_datum": (wf.get("NextDate") or "").strip(),
        "wefact_identifier": str(wf.get("Identifier") or ""),
    }
