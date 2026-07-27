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
                from nixfact_integration.wefact_sync.mapping.creditnota import (
                    creditnota_to_factuur,
                )
                upsert.upsert_creditnota(creditnota_to_factuur(detail), company)
                verwerkt += 1
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


def backfill_crediteuren(client: WeFactClient) -> None:
    from nixfact_integration.wefact_sync.mapping.creditor import creditor_to_supplier
    verwerkt, mislukt = 0, []
    for kop in client.list_all("creditor"):
        code = kop.get("CreditorCode") or ""
        try:
            wf = client.show("creditor", code, "CreditorCode")
            upsert.upsert_supplier(creditor_to_supplier(wf))
            verwerkt += 1
        except Exception as exc:  # noqa: BLE001
            frappe.db.rollback()
            mislukt.append(Mislukking("crediteur", code, str(exc)))
    _rapporteer(verwerkt, mislukt, "crediteuren")


def backfill_inkoop(client: WeFactClient, company: str) -> None:
    from nixfact_integration.wefact_sync.mapping.inkoop import inkoop_to_dict
    from nixfact_integration.wefact_sync.attachments import hang_bijlagen
    verwerkt, mislukt, waarschuwingen = 0, [], []
    for kop in client.list_all("creditinvoice"):
        code = kop.get("CreditInvoiceCode") or ""
        try:
            wf = client.show("creditinvoice", code, "CreditInvoiceCode")
            dic = inkoop_to_dict(wf)
            naam = upsert.upsert_inkoopfactuur(dic, company)
            n = hang_bijlagen(client, naam, dic["attachments"])
            if n < len(dic["attachments"]):
                waarschuwingen.append(f"inkoop {code}: {len(dic['attachments'])-n} bijlage(n) niet gedownload")
            verwerkt += 1
        except Exception as exc:  # noqa: BLE001
            frappe.db.rollback()
            mislukt.append(Mislukking("inkoop", code, str(exc)))
    _rapporteer(verwerkt, mislukt, "inkoop", waarschuwingen)


def vul_ontbrekende_facturen() -> None:
    """Haal alléén de facturen op die nog niet in NIXFact staan.

    Gericht en zacht voor de WeFact-IP-firewall: één lijst-call, daarna een
    detail-fetch (gepacet) uitsluitend voor de ontbrekende facturen. Bedoeld
    om een door de firewall afgebroken backfill af te maken zonder alle 815
    opnieuw op te halen.
    """
    client = _client()
    company = upsert.ensure_company()
    bestaand = set(
        frappe.get_all("NixFact Factuur", pluck="wefact_identifier") or []
    )
    verwerkt, mislukt = 0, []
    waarschuwingen: list[str] = []
    for kop in client.list_all("invoice"):
        wid = str(kop.get("Identifier") or "")
        if wid in bestaand:
            continue
        code = kop.get("InvoiceCode") or ""
        try:
            detail = client.show("invoice", code, "InvoiceCode")
            factuur = invoice_to_factuur(detail)
            if factuur.get("is_creditnota"):
                from nixfact_integration.wefact_sync.mapping.creditnota import (
                    creditnota_to_factuur,
                )

                upsert.upsert_creditnota(creditnota_to_factuur(detail), company)
                verwerkt += 1
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
    _rapporteer(verwerkt, mislukt, "facturen (aanvulling)", waarschuwingen)


def volledige_backfill(alleen: str | None = None) -> None:
    """Bench-entrypoint: importeer debiteuren (eerst) en verkoopfacturen."""
    client = _client()
    company = upsert.ensure_company()
    if alleen in (None, "debiteuren"):
        backfill_debiteuren(client)
    if alleen in (None, "facturen"):
        backfill_facturen(client, company)
    if alleen in (None, "inkoop"):
        backfill_crediteuren(client)
        backfill_inkoop(client, company)
