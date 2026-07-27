# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-inkoopfactuur → NixFact-Inkoopfactuur-dict (plat). Puur."""

from __future__ import annotations


def _btw_percentage(wf: dict) -> float:
    """Hoogste btw-percentage over de regels; Inkoopfactuur is één tarief."""
    pcts = [float(r.get("TaxPercentage") or 0) for r in (wf.get("InvoiceLines") or [])]
    return max(pcts) if pcts else 0.0


def inkoop_to_dict(wf: dict) -> dict:
    return {
        "inkoopfactuur_nr": (wf.get("CreditInvoiceCode") or "").strip(),
        "factuurdatum": (wf.get("Date") or "").strip(),
        "betalingskenmerk": (wf.get("InvoiceCode") or "").strip(),
        "bedrag_excl": float(wf.get("AmountExcl") or 0),
        "btw_percentage": _btw_percentage(wf),
        "wefact_creditor_code": (wf.get("CreditorCode") or "").strip(),
        "wefact_identifier": str(wf.get("Identifier") or ""),
        "attachments": list(wf.get("Attachments") or []),
    }
