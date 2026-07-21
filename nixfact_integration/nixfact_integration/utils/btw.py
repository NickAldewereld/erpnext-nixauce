# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""BTW-categorieën en regelberekening.

Puur rekenwerk: geen frappe-import, geen database. Dit is de enige plek
waar btw-bedragen worden uitgerekend, zodat het doctype, de UBL-builder
en de validator gegarandeerd op dezelfde getallen uitkomen.
"""

from __future__ import annotations

from dataclasses import dataclass

# Nederlandse label -> Peppol UNCL5305-code.
CATEGORIE_CODES: dict[str, str] = {
    "Standaard": "S",
    "Verlegd": "AE",
    "Nultarief": "Z",
    "Vrijgesteld": "E",
}

# Categorieën die verplicht 0% moeten hebben.
NUL_CATEGORIEEN: frozenset[str] = frozenset({"AE", "Z", "E"})

# Peppol eist een reden bij deze categorieën (BR-AE-10, BR-E-10, BR-Z-10).
VRIJSTELLING_REDEN: dict[str, str] = {
    "AE": "Btw verlegd",
    "E": "Vrijgesteld van btw",
    "Z": "Nultarief",
}


def _rond(waarde: float) -> float:
    """Rond af op centen, halve cent omhoog (niet bankers rounding)."""
    from decimal import ROUND_HALF_UP, Decimal

    return float(Decimal(str(waarde)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def code_voor_categorie(label: str) -> str:
    """Vertaal een NL-categorielabel naar een Peppol-code, default 'S'."""
    return CATEGORIE_CODES.get((label or "").strip(), "S")


def regel_excl(aantal: float, eenheidsprijs: float) -> float:
    """Regeltotaal exclusief btw."""
    return _rond(float(aantal or 0) * float(eenheidsprijs or 0))


@dataclass(frozen=True)
class BtwGroep:
    """Eén btw-groep: unieke combinatie van categoriecode en percentage."""

    code: str
    percentage: float
    excl: float
    btw: float


def groepeer_btw(regels: list[dict]) -> list[BtwGroep]:
    """Groepeer regels per (code, percentage) en bereken btw per groep.

    Btw wordt berekend over het groepstotaal, niet per regel opgeteld —
    Peppol BR-CO-17 eist dat TaxAmount volgt uit TaxableAmount x rate.
    """
    buckets: dict[tuple[str, float], float] = {}
    for regel in regels:
        code = regel.get("btw_code") or "S"
        pct = float(regel.get("btw_percentage") or 0)
        sleutel = (code, pct)
        buckets[sleutel] = _rond(buckets.get(sleutel, 0.0) + float(regel["excl"]))

    resultaat = []
    for (code, pct), excl in sorted(buckets.items()):
        resultaat.append(BtwGroep(code, pct, excl, _rond(excl * pct / 100)))
    return resultaat


def totalen(regels: list[dict]) -> dict:
    """Factuurtotalen: excl, btw, incl."""
    groepen = groepeer_btw(regels)
    excl = _rond(sum(g.excl for g in groepen))
    btw = _rond(sum(g.btw for g in groepen))
    return {"excl": excl, "btw": btw, "incl": _rond(excl + btw)}
