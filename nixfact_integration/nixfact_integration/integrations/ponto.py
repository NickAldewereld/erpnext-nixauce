# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Integration with the Ponto (Isabel Group) banking API."""

from __future__ import annotations

import frappe
import requests
from frappe import _
from frappe.utils import flt, get_datetime


def _redact(text: str, *secrets: str) -> str:
    """Strip known secrets from a string before logging."""
    out = text or ""
    for s in secrets:
        if s:
            out = out.replace(s, "[REDACTED]")
    return out[:500]


class PontoIntegration:
    BASE_URL = "https://api.myponto.com"
    TOKEN_URL = "https://api.myponto.com/oauth2/token"

    def __init__(self, bank_koppeling) -> None:
        if isinstance(bank_koppeling, str):
            bank_koppeling = frappe.get_doc("NixFact Bank Koppeling", bank_koppeling)

        self.koppeling = bank_koppeling
        self.client_id = bank_koppeling.ponto_client_id
        self.client_secret = bank_koppeling.get_password("ponto_client_secret")
        self.refresh_token = bank_koppeling.get_password("ponto_refresh_token")
        self.account_id = bank_koppeling.account_id
        self.access_token: str | None = None

        if not (self.client_id and self.client_secret and self.refresh_token):
            frappe.throw(
                _("Ponto-credentials zijn niet volledig op deze bankkoppeling.")
            )

    def authenticate(self) -> str:
        """Obtain an access token using the stored refresh token."""
        try:
            response = requests.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                },
                auth=(self.client_id, self.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
        except requests.RequestException as e:
            frappe.log_error(
                title="Ponto authenticatie — netwerkfout",
                message=_redact(str(e), self.client_secret, self.refresh_token),
            )
            frappe.throw(_("Ponto API fout: kon geen verbinding maken."))

        if response.status_code != 200:
            frappe.log_error(
                title="Ponto authenticatie mislukt",
                message=_redact(
                    f"Status {response.status_code}: {response.text}",
                    self.client_secret,
                    self.refresh_token,
                ),
            )
            frappe.throw(
                _("Ponto authenticatie mislukt: {0}").format(response.status_code)
            )

        data = response.json()
        self.access_token = data["access_token"]

        # Persist the rotated refresh token immediately. Going through
        # doc.save() ensures the Password fieldtype is encrypted at rest;
        # frappe.db.set_value would store plaintext and break get_password().
        new_refresh = data.get("refresh_token")
        if new_refresh and new_refresh != self.refresh_token:
            try:
                koppeling = frappe.get_doc(
                    "NixFact Bank Koppeling", self.koppeling.name
                )
                koppeling.ponto_refresh_token = new_refresh
                koppeling.save(ignore_permissions=True)
                frappe.db.commit()  # critical: do not roll back the rotation
                self.refresh_token = new_refresh
            except Exception:  # noqa: BLE001
                frappe.log_error(
                    title="Ponto refresh token opslaan mislukt",
                    message=frappe.get_traceback(),
                )
                # Old refresh token has likely been invalidated by Ponto,
                # so the koppeling will need re-OAuth. Surface to the user.
                frappe.throw(
                    _(
                        "Kon vernieuwd Ponto-token niet opslaan; "
                        "her-koppel de bankrekening."
                    )
                )

        return self.access_token

    def get_transactions(self, after: str | None = None, limit: int = 100) -> list[dict]:
        """Fetch a page of transactions from Ponto."""
        if not self.access_token:
            self.authenticate()

        url = f"{self.BASE_URL}/accounts/{self.account_id}/transactions"
        params: dict[str, str | int] = {"limit": min(int(limit), 100)}
        if after:
            params["after"] = after

        try:
            response = requests.get(
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json",
                },
                timeout=30,
            )
        except requests.RequestException as e:
            frappe.log_error(
                title="Ponto transacties — netwerkfout",
                message=_redact(str(e), self.access_token, self.client_secret),
            )
            frappe.throw(_("Ponto API fout: kon geen verbinding maken."))

        if response.status_code != 200:
            frappe.log_error(
                title="Ponto transacties ophalen mislukt",
                message=_redact(
                    f"Status {response.status_code}: {response.text}",
                    self.access_token,
                    self.client_secret,
                    self.refresh_token,
                ),
            )
            frappe.throw(_("Ponto API fout: {0}").format(response.status_code))

        return response.json().get("data", [])

    def parse_transactions(self, raw_transactions: list[dict]) -> list[dict]:
        """Normalize Ponto API responses to NixFact Bank Transactie shape.

        ``omschrijving`` concatenates structured + unstructured remittance
        info so the matching engine has both available even if Ponto only
        emits one.
        """
        parsed = []
        for txn in raw_transactions:
            attrs = txn.get("attributes", {}) or {}

            structured = (attrs.get("remittanceInformationStructured") or "").strip()
            unstructured = (attrs.get("remittanceInformation") or "").strip()
            description = (attrs.get("description") or "").strip()
            joined = " | ".join(p for p in (description, unstructured, structured) if p)

            parsed.append(
                {
                    "transactie_id": txn.get("id", ""),
                    "datum": (
                        attrs.get("executionDate")
                        or attrs.get("valueDate", "")
                    ),
                    "bedrag": flt(attrs.get("amount", 0), 2),
                    "van_naar": (attrs.get("counterpartReference") or "").strip(),
                    "naam": (attrs.get("counterpartName") or "").strip(),
                    "omschrijving": joined,
                    "referentie": structured or unstructured,
                }
            )
        return parsed

    def sync(self) -> dict[str, int]:
        """Pull new transactions and insert them. Idempotent on transactie_id."""
        self.authenticate()

        raw = self.get_transactions()
        parsed = self.parse_transactions(raw)

        imported = 0
        skipped = 0

        for txn in parsed:
            if not txn["transactie_id"]:
                skipped += 1
                continue
            if frappe.db.exists(
                "NixFact Bank Transactie",
                {"transactie_id": txn["transactie_id"]},
            ):
                skipped += 1
                continue

            doc = frappe.get_doc(
                {
                    "doctype": "NixFact Bank Transactie",
                    "transactie_id": txn["transactie_id"],
                    "bank_koppeling": self.koppeling.name,
                    "datum": txn["datum"],
                    "bedrag": txn["bedrag"],
                    "van_naar": txn["van_naar"],
                    "naam": txn["naam"],
                    "omschrijving": txn["omschrijving"],
                    "referentie": txn["referentie"],
                    "status": "Onverwerkt",
                }
            )
            doc.insert(ignore_permissions=True)  # cron-only; perms enforced upstream
            imported += 1

        frappe.db.set_value(
            "NixFact Bank Koppeling",
            self.koppeling.name,
            "laatste_sync",
            get_datetime(),
            update_modified=False,
        )
        frappe.db.commit()

        return {"imported": imported, "skipped": skipped}
