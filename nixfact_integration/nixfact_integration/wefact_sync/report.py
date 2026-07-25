# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Puur runrapport voor de WeFact-import. Geen frappe."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mislukking:
    entiteit: str
    code: str
    reden: str


def vat_rapport(
    verwerkt: int,
    mislukt: list[Mislukking],
    soort: str,
    waarschuwingen: list[str] | None = None,
) -> str:
    regels = [f"WeFact-import {soort}: {verwerkt} verwerkt, {len(mislukt)} mislukt."]
    for m in mislukt:
        regels.append(f"- {m.entiteit} {m.code}: {m.reden}")
    if waarschuwingen:
        regels.append(f"{len(waarschuwingen)} waarschuwing(en):")
        for w in waarschuwingen:
            regels.append(f"- {w}")
    return "\n".join(regels)
