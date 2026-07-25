# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Orkestratie van de WeFact→NIXFact backfill.

Per-record geïsoleerd: één fout stopt de rest niet. Aan het eind een
zichtbaar rapport (scheduler-log + geconsolideerde Error Log).
"""

from __future__ import annotations

import frappe

from nixfact_integration.wefact_sync.client import WeFactClient
from nixfact_integration.wefact_sync.mapping.debtor import (
    debtor_to_address,
    debtor_to_customer,
)
from nixfact_integration.wefact_sync.mapping.invoice import invoice_to_factuur
from nixfact_integration.wefact_sync.report import Mislukking, vat_rapport
from nixfact_integration.wefact_sync import upsert


def _client() -> WeFactClient:
    settings = frappe.get_single("NixFact Instellingen")
    key = settings.get_password("wefact_api_key")
    return WeFactClient(api_key=key)


def _rapporteer(
    verwerkt: int,
    mislukt: list[Mislukking],
    soort: str,
    waarschuwingen: list[str] | None = None,
) -> None:
    tekst = vat_rapport(verwerkt, mislukt, soort, waarschuwingen)
    frappe.logger("nixfact", allow_site=True).warning(tekst)
    if mislukt or waarschuwingen:
        frappe.log_error(title=f"WeFact-import {soort}", message=tekst)


def backfill_debiteuren(client: WeFactClient) -> None:
    verwerkt, mislukt = 0, []
    for kop in client.list_all("debtor"):
        code = kop.get("DebtorCode") or ""
        try:
            # De debiteurenlijst is schraal (geen adres/BTW-nummer); die
            # zitten alleen in het detail, dus per debiteur ophalen.
            wf = client.show("debtor", code, "DebtorCode")
            upsert.upsert_customer(debtor_to_customer(wf), debtor_to_address(wf))
            verwerkt += 1
        except Exception as exc:  # noqa: BLE001
            frappe.db.rollback()
            mislukt.append(Mislukking("debiteur", code, str(exc)))
    _rapporteer(verwerkt, mislukt, "debiteuren")


def backfill_facturen(client: WeFactClient, company: str) -> None:
    verwerkt, mislukt = 0, []
    waarschuwingen: list[str] = []
    for kop in client.list_all("invoice"):
        code = kop.get("InvoiceCode") or ""
        try:
            detail = client.show("invoice", code, "InvoiceCode")
            factuur = invoice_to_factuur(detail)
            if factuur.get("is_creditnota"):
                waarschuwingen.append(
                    f"factuur {code}: creditnota overgeslagen (afhandeling volgt in vervolgfase)"
                )
                continue
            upsert.upsert_factuur(factuur, company)
            verwerkt += 1
            if factuur.get("onbekende_status"):
                waarschuwingen.append(
                    f"factuur {code}: onbekende WeFact-status, geïmporteerd als Concept"
                )
        except Exception as exc:  # noqa: BLE001
            frappe.db.rollback()
            mislukt.append(Mislukking("factuur", code, str(exc)))
    _rapporteer(verwerkt, mislukt, "facturen", waarschuwingen)


def volledige_backfill(alleen: str | None = None) -> None:
    """Bench-entrypoint: importeer debiteuren (eerst) en verkoopfacturen."""
    client = _client()
    company = upsert.ensure_company()
    if alleen in (None, "debiteuren"):
        backfill_debiteuren(client)
    if alleen in (None, "facturen"):
        backfill_facturen(client, company)
