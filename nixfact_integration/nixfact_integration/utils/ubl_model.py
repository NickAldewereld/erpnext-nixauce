# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Datamodel voor een uitgaande e-factuur.

Bewust vrij van frappe: de builder en de validator werken uitsluitend op
deze dataclasses, waardoor ze in CI volledig getest kunnen worden.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nixfact_integration.utils.btw import BtwGroep, groepeer_btw, totalen


@dataclass
class UBLPartij:
    """Leverancier of afnemer."""

    naam: str = ""
    btw_nummer: str = ""
    straat: str = ""
    extra_straat: str = ""
    plaats: str = ""
    postcode: str = ""
    landcode: str = "NL"
    email: str = ""
    telefoon: str = ""


@dataclass
class UBLRegel:
    """Eén factuurregel, al doorgerekend."""

    omschrijving: str
    aantal: float
    eenheidsprijs: float
    excl: float
    btw_percentage: float
    btw_code: str = "S"


@dataclass
class UBLFactuur:
    """Een complete uitgaande factuur."""

    nummer: str
    factuurdatum: str
    vervaldatum: str = ""
    referentie: str = ""
    leverancier: UBLPartij = field(default_factory=UBLPartij)
    afnemer: UBLPartij = field(default_factory=UBLPartij)
    regels: list[UBLRegel] = field(default_factory=list)
    iban: str = ""
    bic: str = ""
    betaald_bedrag: float = 0.0
    opmerkingen: str = ""

    def _als_dicts(self) -> list[dict]:
        return [
            {
                "excl": r.excl,
                "btw_percentage": r.btw_percentage,
                "btw_code": r.btw_code,
            }
            for r in self.regels
        ]

    def btw_groepen(self) -> list[BtwGroep]:
        return groepeer_btw(self._als_dicts())

    def totalen(self) -> dict:
        return totalen(self._als_dicts())
