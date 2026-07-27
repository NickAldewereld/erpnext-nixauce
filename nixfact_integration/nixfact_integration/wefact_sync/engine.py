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


def backfill_abonnementen(client: WeFactClient) -> None:
    from nixfact_integration.wefact_sync.mapping.abonnement import abonnement_to_dict
    verwerkt, mislukt = 0, []
    for kop in client.list_all("subscription"):
        ident = str(kop.get("Identifier") or "")
        try:
            wf = client.show("subscription", ident, "Identifier")
            upsert.upsert_abonnement(abonnement_to_dict(wf))
            verwerkt += 1
        except Exception as exc:  # noqa: BLE001
            frappe.db.rollback()
            mislukt.append(Mislukking("abonnement", ident, str(exc)))
    _rapporteer(verwerkt, mislukt, "abonnementen")


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


def incrementele_sync() -> None:
    """Scheduler-entrypoint: verwerk alleen records die WeFact wijzigde.

    Lijst per entiteit met ``modified_since=cursor`` — WeFact geeft dan
    alleen gewijzigde records terug, dus normaal een handvol per uur (geen
    burst die de IP-firewall triggert). Alleen die records krijgen een
    detail-fetch + upsert. De cursor schuift alleen op tot de hoogste
    Modified die veilig is — nooit voorbij een mislukt record, anders wordt
    dat record bij de volgende run permanent overgeslagen.
    Debiteuren met een lege ``Modified`` worden hier gemist; een dagelijkse
    volledige debiteuren-backfill (``dagelijkse_debiteuren_sync``) vangt die.
    """
    from nixfact_integration.wefact_sync import cursor

    settings = frappe.get_single("NixFact Instellingen")
    if not settings.wefact_sync_enabled:
        return
    client = _client()
    company = upsert.ensure_company()

    # Debiteuren
    sinds = cursor.lees_cursor("debtor")
    gewijzigd = client.list_all(
        "debtor", params={"modified": {"from": sinds}} if sinds else None
    )
    mislukt: list[Mislukking] = []
    succes_mod: list[str] = []
    fout_mod: list[str] = []
    for kop in gewijzigd:
        code = kop.get("DebtorCode") or ""
        mod = str(kop.get("Modified") or "")
        try:
            wf = client.show("debtor", code, "DebtorCode")
            upsert.upsert_customer(debtor_to_customer(wf), debtor_to_address(wf))
            succes_mod.append(mod)
        except Exception as exc:  # noqa: BLE001
            frappe.db.rollback()
            fout_mod.append(mod)
            mislukt.append(Mislukking("debiteur", code, str(exc)))
    # Cursor alleen veilig opschuiven: nooit voorbij de vroegste mislukking.
    if fout_mod:
        grens = min(m for m in fout_mod if m) if any(fout_mod) else ""
        veilig = [m for m in succes_mod if m and (not grens or m < grens)]
        nieuwe_cursor = max(veilig) if veilig else cursor.lees_cursor("debtor")
    else:
        nieuwe_cursor = cursor.max_modified(gewijzigd)
    cursor.schrijf_cursor("debtor", nieuwe_cursor)
    _rapporteer(len(succes_mod), mislukt, "debiteuren (sync)")

    # Facturen (incl. creditnota's)
    sinds = cursor.lees_cursor("invoice")
    gewijzigd = client.list_all(
        "invoice", params={"modified": {"from": sinds}} if sinds else None
    )
    mislukt = []
    waarschuwingen: list[str] = []
    succes_mod = []
    fout_mod = []
    for kop in gewijzigd:
        code = kop.get("InvoiceCode") or ""
        mod = str(kop.get("Modified") or "")
        try:
            detail = client.show("invoice", code, "InvoiceCode")
            factuur = invoice_to_factuur(detail)
            if factuur.get("is_creditnota"):
                from nixfact_integration.wefact_sync.mapping.creditnota import (
                    creditnota_to_factuur,
                )
                upsert.upsert_creditnota(creditnota_to_factuur(detail), company)
            else:
                upsert.upsert_factuur(factuur, company)
                if factuur.get("onbekende_status"):
                    waarschuwingen.append(
                        f"factuur {code}: onbekende WeFact-status, geïmporteerd als Concept"
                    )
            succes_mod.append(mod)
        except Exception as exc:  # noqa: BLE001
            frappe.db.rollback()
            fout_mod.append(mod)
            mislukt.append(Mislukking("factuur", code, str(exc)))
    # Cursor alleen veilig opschuiven: nooit voorbij de vroegste mislukking.
    if fout_mod:
        grens = min(m for m in fout_mod if m) if any(fout_mod) else ""
        veilig = [m for m in succes_mod if m and (not grens or m < grens)]
        nieuwe_cursor = max(veilig) if veilig else cursor.lees_cursor("invoice")
    else:
        nieuwe_cursor = cursor.max_modified(gewijzigd)
    cursor.schrijf_cursor("invoice", nieuwe_cursor)
    _rapporteer(len(succes_mod), mislukt, "facturen (sync)", waarschuwingen)


def dagelijkse_debiteuren_sync() -> None:
    """Dagelijkse volledige debiteuren-sync — vangt debiteuren met een lege
    WeFact-`Modified` die de uurlijkse incrementele sync mist. Gepacet en
    idempotent; ~276 calls/dag, ruim binnen de WeFact-limieten.
    """
    settings = frappe.get_single("NixFact Instellingen")
    if not settings.wefact_sync_enabled:
        return
    client = _client()
    backfill_debiteuren(client)


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
    if alleen in (None, "abonnementen"):
        backfill_abonnementen(client)
