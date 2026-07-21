# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Validatie van een UBLFactuur tegen de belangrijkste EN16931-regels.

Doel is niet volledige schematron-dekking maar het afvangen van de fouten
die in de praktijk voorkomen, met een melding die een boekhouder begrijpt.
De ontvangende access point valideert alsnog volledig; dit voorkomt dat
een factuur daar pas sneuvelt.
"""

from __future__ import annotations

from dataclasses import dataclass

from nixfact_integration.utils.btw import CATEGORIE_CODES, NUL_CATEGORIEEN
from nixfact_integration.utils.ubl_model import UBLFactuur

GELDIGE_CODES = frozenset(CATEGORIE_CODES.values())


@dataclass(frozen=True)
class Fout:
    """Eén validatiefout: de EN16931-regel plus een leesbare melding."""

    regel: str
    melding: str


def valideer(factuur: UBLFactuur) -> list[Fout]:
    """Geef alle gevonden fouten terug; een lege lijst betekent geldig."""
    fouten: list[Fout] = []
    fouten.extend(_controleer_kop(factuur))
    fouten.extend(_controleer_partijen(factuur))
    fouten.extend(_controleer_regels(factuur))
    return fouten


def _controleer_kop(factuur: UBLFactuur) -> list[Fout]:
    fouten = []
    if not (factuur.nummer or "").strip():
        fouten.append(
            Fout("BR-02", "De factuur heeft geen factuurnummer.")
        )
    if not (factuur.factuurdatum or "").strip():
        fouten.append(Fout("BR-03", "De factuur heeft geen factuurdatum."))
    if not factuur.regels:
        fouten.append(
            Fout("BR-16", "De factuur heeft geen regels; voeg minstens "
                 "één factuurregel toe.")
        )
    return fouten


def _controleer_partijen(factuur: UBLFactuur) -> list[Fout]:
    fouten = []
    lev, afn = factuur.leverancier, factuur.afnemer

    if not (lev.naam or "").strip():
        fouten.append(
            Fout("BR-06", "De naam van je eigen bedrijf ontbreekt. Vul die "
                 "aan bij het bedrijf in de instellingen.")
        )
    if not (afn.naam or "").strip():
        fouten.append(Fout("BR-07", "De naam van de klant ontbreekt."))
    if not (lev.plaats or "").strip() or not (lev.landcode or "").strip():
        fouten.append(
            Fout("BR-08", "Het adres van je eigen bedrijf is onvolledig: "
                 "plaats en land zijn verplicht.")
        )
    if not (afn.landcode or "").strip():
        fouten.append(
            Fout("BR-09", "Het land van de klant ontbreekt in het adres.")
        )
    return fouten


def _controleer_regels(factuur: UBLFactuur) -> list[Fout]:
    fouten = []
    for nummer, regel in enumerate(factuur.regels, start=1):
        if not (regel.omschrijving or "").strip():
            fouten.append(
                Fout("BR-25", f"Regel {nummer} heeft geen omschrijving.")
            )

        if regel.btw_code not in GELDIGE_CODES:
            fouten.append(
                Fout("BR-CL-01", f"Regel {nummer} heeft een onbekende "
                     f"btw-categorie ({regel.btw_code}).")
            )
            continue

        verwacht = round(float(regel.aantal) * float(regel.eenheidsprijs), 2)
        if abs(verwacht - float(regel.excl)) > 0.01:
            fouten.append(
                Fout("BR-CO-04", f"Regel {nummer}: het regeltotaal "
                     f"({regel.excl:.2f}) klopt niet met aantal x prijs "
                     f"({verwacht:.2f}).")
            )

        pct = float(regel.btw_percentage or 0)
        if regel.btw_code in NUL_CATEGORIEEN and pct != 0:
            fouten.append(
                Fout(f"BR-{regel.btw_code}-01", f"Regel {nummer} heeft "
                     f"categorie {regel.btw_code}; daarbij moet het "
                     f"btw-percentage 0 zijn, niet {pct:.0f}.")
            )
        if regel.btw_code == "S" and pct <= 0:
            fouten.append(
                Fout("BR-S-01", f"Regel {nummer} is standaard belast maar "
                     "heeft geen btw-percentage.")
            )
        if regel.btw_code == "AE" and not (
            factuur.afnemer.btw_nummer or ""
        ).strip():
            fouten.append(
                Fout("BR-AE-09", f"Regel {nummer} is btw-verlegd; dan is het "
                     "btw-nummer van de klant verplicht.")
            )
    return fouten
