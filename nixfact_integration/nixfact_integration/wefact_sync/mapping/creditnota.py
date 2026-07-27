# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-verkoop-creditnota → NixFact-Factuur-dict (negatief). Puur."""

from __future__ import annotations

from nixfact_integration.wefact_sync.mapping.invoice import (
    btw_categorie,
    strip_html,
)
from nixfact_integration.wefact_sync.mapping.status import nixfact_status


def _neg(bedrag: float) -> float:
    """Forceer een negatief bedrag (creditnota); positief wordt omgekeerd."""
    b = float(bedrag or 0)
    return -abs(b)


def _regel(wf_line: dict) -> dict:
    pct = float(wf_line.get("TaxPercentage") or 0)
    return {
        "omschrijving": strip_html(wf_line.get("Description")),
        "aantal": float(wf_line.get("Number") or 0),
        "eenheidsprijs": _neg(wf_line.get("PriceExcl")),
        "btw_categorie": btw_categorie(wf_line.get("TaxCode"), pct),
        "btw_percentage": pct,
    }


def creditnota_to_factuur(wf: dict) -> dict:
    res = nixfact_status(
        (wf.get("Translations") or {}).get("Status") or "",
        float(wf.get("AmountIncl") or 0),
    )
    return {
        "factuurnummer": (wf.get("InvoiceCode") or "").strip(),
        "factuur_datum": (wf.get("Date") or "").strip(),
        "referentie": (wf.get("ReferenceNumber") or "").strip(),
        "wefact_identifier": str(wf.get("Identifier") or ""),
        "wefact_debtor_code": (wf.get("DebtorCode") or "").strip(),
        "status": res.status,
        "is_creditnota": True,
        "origineel_wefact_id": str(wf.get("OriginalInvoice") or ""),
        "onbekende_status": res.onbekend,
        "regels": [_regel(line) for line in (wf.get("InvoiceLines") or [])],
    }
