# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-statustekst → NIXFact-status, plus creditnota-detectie.

WeFacts numerieke statuscodes wijken af van hun eigen documentatie; de
tekst uit ``Translations.Status`` is de betrouwbare bron. Onbekende
statussen vallen veilig terug op 'Concept' met een vlag, zodat een nieuwe
WeFact-status nooit stil verkeerd landt.
"""

from __future__ import annotations

from dataclasses import dataclass

# WeFact-statustekst (lowercase) → NIXFact-status.
_STATUS_MAP = {
    "concept": "Concept",
    "verzonden": "Verstuurd",
    "verstuurd": "Verstuurd",
    "betaald": "Betaald",
    "verlopen": "Verstuurd",
    "herinnering": "Verstuurd",
    "aanmaning": "Verstuurd",
    "gedeeltelijk betaald": "Verstuurd",
    "creditfactuur": "Betaald",
    "oninbaar": "Oninbaar",
}


@dataclass(frozen=True)
class StatusResultaat:
    status: str
    is_creditnota: bool
    onbekend: bool


def nixfact_status(status_tekst: str, bedrag_incl: float) -> StatusResultaat:
    tekst = (status_tekst or "").strip().lower()
    status = _STATUS_MAP.get(tekst)
    onbekend = status is None
    if onbekend:
        status = "Concept"
    is_credit = float(bedrag_incl or 0) < 0 or "credit" in tekst
    return StatusResultaat(status=status, is_creditnota=is_credit, onbekend=onbekend)
