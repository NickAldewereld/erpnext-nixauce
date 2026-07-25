# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-verkoopfactuur → NixFact-Factuur-dict. Puur, frappe-vrij."""

from __future__ import annotations

import re

from nixfact_integration.wefact_sync.mapping.status import nixfact_status

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(tekst: str) -> str:
    """Verwijder HTML-tags en normaliseer witruimte in een omschrijving.

    WeFact-regelomschrijvingen bevatten opmaak (<strong>, <b>) en zijn soms
    hele alinea's; als platte tekst passen ze in het Small-Text-veld.
    """
    zonder = _HTML_TAG_RE.sub("", tekst or "")
    return _WS_RE.sub(" ", zonder).strip()


def btw_categorie(tax_code: str, tax_percentage: float) -> str:
    """Leid de NIXFact-btw-categorie af uit WeFact tax-code + percentage."""
    code = (tax_code or "").upper()
    if "VERLEGD" in code or code.endswith("VS"):
        return "Verlegd"
    if float(tax_percentage or 0) == 0:
        return "Nultarief"
    return "Standaard"


def _regel(wf_line: dict) -> dict:
    pct = float(wf_line.get("TaxPercentage") or 0)
    return {
        "omschrijving": strip_html(wf_line.get("Description")),
        "aantal": float(wf_line.get("Number") or 0),
        "eenheidsprijs": float(wf_line.get("PriceExcl") or 0),
        "btw_categorie": btw_categorie(wf_line.get("TaxCode"), pct),
        "btw_percentage": pct,
    }


def invoice_to_factuur(wf: dict) -> dict:
    bedrag_incl = float(wf.get("AmountIncl") or 0)
    status_tekst = (wf.get("Translations") or {}).get("Status") or ""
    res = nixfact_status(status_tekst, bedrag_incl)
    return {
        "factuurnummer": (wf.get("InvoiceCode") or "").strip(),
        "factuur_datum": (wf.get("Date") or "").strip(),
        "referentie": (wf.get("ReferenceNumber") or "").strip(),
        "wefact_identifier": str(wf.get("Identifier") or ""),
        "wefact_debtor_code": (wf.get("DebtorCode") or "").strip(),
        "status": res.status,
        "is_creditnota": res.is_creditnota,
        "onbekende_status": res.onbekend,
        "regels": [_regel(line) for line in (wf.get("InvoiceLines") or [])],
    }
