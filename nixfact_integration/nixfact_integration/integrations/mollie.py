# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Mollie payment integration for NIXFact invoices."""

from __future__ import annotations

import re
from urllib.parse import quote

import frappe
import requests
from frappe import _
from frappe.utils import flt, get_url, getdate, nowdate

# Mollie payment ID format: tr_ followed by alphanumeric. Bound the length
# so that an attacker can't blast a 1MB string into our DB query.
PAYMENT_ID_PATTERN = re.compile(r"^tr_[a-zA-Z0-9]{4,40}$")
PAYMENT_ID_MAX_LEN = 64

# Mollie payment statuses that mean "the customer's money arrived".
PAID_STATUSES = {"paid"}
# Statuses that mean the payment is dead — invoice should NOT show as paid.
TERMINAL_FAILED_STATUSES = {"failed", "canceled", "expired"}
# Refund-related statuses we want to surface as "no longer paid".
REFUND_STATUSES = {"refunded", "charged_back"}


def _redact(text: str, *secrets: str) -> str:
    """Strip known secrets from a string before logging."""
    out = text or ""
    for s in secrets:
        if s:
            out = out.replace(s, "[REDACTED]")
    return out[:500]


class MollieIntegration:
    """Client for the Mollie v2 payments API."""

    BASE_URL = "https://api.mollie.com/v2"

    def __init__(self, api_key: str | None = None) -> None:
        if api_key:
            self.api_key = api_key
        else:
            settings = frappe.get_single("NixFact Instellingen")
            if not settings.mollie_enabled:
                frappe.throw(_("Mollie is niet ingeschakeld in de instellingen."))
            self.api_key = settings.get_password("mollie_api_key")

        if not self.api_key:
            frappe.throw(_("Mollie API key is niet geconfigureerd."))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def create_payment(self, factuur) -> str:
        """Create a Mollie payment and store the checkout URL on the invoice.

        We use ``db_set`` (and not ``save``) to write only the three
        Mollie-specific fields. A full save would otherwise re-run validate()
        with stale in-memory state and could clobber a status update written
        by a webhook firing in parallel.
        """
        if isinstance(factuur, str):
            factuur = frappe.get_doc("NixFact Factuur", factuur)

        amount = flt(factuur.bedrag_incl_btw, 2)
        if amount <= 0:
            frappe.throw(_("Factuurbedrag moet groter zijn dan 0."))

        site_url = get_url()
        if not site_url.startswith("https://"):
            frappe.throw(
                _(
                    "Mollie vereist een publieke HTTPS site URL. "
                    "Configureer 'host_name' in site_config voordat je betaallinks aanmaakt."
                )
            )

        try:
            response = requests.post(
                f"{self.BASE_URL}/payments",
                json={
                    "amount": {
                        "currency": "EUR",
                        "value": f"{amount:.2f}",
                    },
                    "description": f"Factuur {factuur.factuurnummer}",
                    "redirectUrl": (
                        f"{site_url}/payment-success?factuur="
                        f"{quote(factuur.name, safe='')}"
                    ),
                    "webhookUrl": (
                        f"{site_url}/api/method/"
                        "nixfact_integration.integrations.mollie.webhook"
                    ),
                    "metadata": {
                        "factuur_name": factuur.name,
                        "factuurnummer": factuur.factuurnummer,
                    },
                },
                headers=self._headers(),
                timeout=30,
            )
        except requests.RequestException as e:
            frappe.log_error(
                title="Mollie payment aanmaken — netwerkfout",
                message=_redact(str(e), self.api_key),
            )
            frappe.throw(_("Mollie API fout: kon geen verbinding maken."))

        if response.status_code not in (200, 201):
            frappe.log_error(
                title="Mollie payment aanmaken mislukt",
                message=_redact(
                    f"Status {response.status_code}: {response.text}",
                    self.api_key,
                ),
            )
            frappe.throw(_("Mollie API fout: {0}").format(response.status_code))

        try:
            data = response.json()
        except ValueError:
            frappe.throw(_("Mollie API gaf geen geldige JSON terug."))

        payment_id = data.get("id")
        checkout_url = (
            data.get("_links", {}).get("checkout", {}).get("href")
        )
        if not payment_id or not checkout_url:
            frappe.log_error(
                title="Mollie payment: onverwachte response",
                message=_redact(str(data)[:500], self.api_key),
            )
            frappe.throw(_("Mollie gaf onvolledige betaalgegevens terug."))

        # Race-safe write: only the three Mollie fields, no validate() rerun.
        frappe.db.set_value(
            "NixFact Factuur",
            factuur.name,
            {
                "mollie_payment_id": payment_id,
                "mollie_payment_url": checkout_url,
                "betaallink": checkout_url,
            },
            update_modified=False,
        )
        frappe.db.commit()

        return checkout_url

    def get_payment(self, payment_id: str) -> dict:
        """Fetch payment status from Mollie."""
        if (
            not payment_id
            or len(payment_id) > PAYMENT_ID_MAX_LEN
            or not PAYMENT_ID_PATTERN.match(payment_id)
        ):
            frappe.throw(_("Ongeldig Mollie payment ID."))

        try:
            response = requests.get(
                f"{self.BASE_URL}/payments/{payment_id}",
                headers=self._headers(),
                timeout=30,
            )
        except requests.RequestException as e:
            frappe.log_error(
                title="Mollie payment ophalen — netwerkfout",
                message=_redact(str(e), self.api_key),
            )
            frappe.throw(_("Mollie API fout: kon geen verbinding maken."))

        if response.status_code != 200:
            frappe.log_error(
                title="Mollie payment ophalen mislukt",
                message=_redact(
                    f"Status {response.status_code}: {response.text}",
                    self.api_key,
                ),
            )
            frappe.throw(_("Mollie API fout: {0}").format(response.status_code))

        try:
            return response.json()
        except ValueError:
            frappe.throw(_("Mollie API gaf geen geldige JSON terug."))


@frappe.whitelist(allow_guest=True)
def webhook():
    """Handle Mollie payment webhook.

    Guest-accessible because Mollie has no shared secret. We never trust
    the webhook body for state — the payment status is re-fetched from
    Mollie before any DB write. The endpoint is idempotent: a re-delivery
    for a payment we already settled returns immediately without writes.
    """
    payment_id = frappe.form_dict.get("id")
    if (
        not payment_id
        or len(str(payment_id)) > PAYMENT_ID_MAX_LEN
        or not PAYMENT_ID_PATTERN.match(str(payment_id))
    ):
        return "OK"

    factuur_name = frappe.db.get_value(
        "NixFact Factuur",
        {"mollie_payment_id": payment_id},
        "name",
    )
    if not factuur_name:
        # Mollie may legitimately ping us for IDs we don't know (e.g.
        # a payment was deleted before settlement). Acknowledge — no retry.
        return "OK"

    try:
        mollie = MollieIntegration()
        payment_data = mollie.get_payment(payment_id)
    except Exception:  # noqa: BLE001 — log full traceback server-side
        frappe.log_error(
            title="Mollie webhook: status ophalen mislukt",
            message=frappe.get_traceback(),
        )
        # 503 so Mollie retries this — transient failure path.
        frappe.local.response.http_status_code = 503
        return "RETRY"

    status = payment_data.get("status")

    if status in PAID_STATUSES:
        _settle_paid(factuur_name, payment_data)
    elif status in TERMINAL_FAILED_STATUSES:
        _mark_payment_failed(factuur_name, status)
    elif status in REFUND_STATUSES:
        _mark_payment_refunded(factuur_name, status, payment_data)
    # Other statuses (open, pending, authorized) we ignore: nothing to do yet.

    return "OK"


def _settle_paid(factuur_name: str, payment_data: dict) -> None:
    """Idempotent: mark invoice paid using Mollie's authoritative payload.

    Uses a row-level lock so a concurrent bank-matching settle doesn't
    double-count the payment.
    """
    # Lock the row first — `for_update=True` issues SELECT … FOR UPDATE.
    current_status = frappe.db.get_value(
        "NixFact Factuur",
        factuur_name,
        "status",
        for_update=True,
    )
    if current_status == "Betaald":
        return  # already settled — no-op on webhook retries

    paid_at = payment_data.get("paidAt")
    betaaldatum = nowdate()
    if paid_at:
        try:
            betaaldatum = getdate(paid_at)
        except Exception:  # noqa: BLE001
            betaaldatum = nowdate()

    factuur = frappe.get_doc("NixFact Factuur", factuur_name)
    bedrag = flt(factuur.bedrag_incl_btw, 2)
    factuur.betaald_bedrag = bedrag
    factuur.betaaldatum = betaaldatum
    factuur.openstaand_bedrag = 0
    factuur.status = "Betaald"
    factuur.save(ignore_permissions=True)  # webhook runs as Guest, expected
    frappe.db.commit()


def _mark_payment_failed(factuur_name: str, status: str) -> None:
    """Record a failed/expired/canceled payment without changing invoice state."""
    frappe.db.set_value(
        "NixFact Factuur",
        factuur_name,
        {"mollie_payment_id": "", "mollie_payment_url": "", "betaallink": ""},
        update_modified=False,
    )
    frappe.logger("nixfact").info(
        "Mollie payment %s for factuur %s: %s — link cleared",
        factuur_name,
        factuur_name,
        status,
    )
    frappe.db.commit()


def _mark_payment_refunded(factuur_name: str, status: str, payment_data: dict) -> None:
    """Mollie reported a refund or chargeback. Flag the invoice for review."""
    frappe.logger("nixfact").info(
        "Mollie payment %s refunded/charged-back: %s — flagging factuur for review",
        factuur_name,
        status,
    )
    # Don't auto-flip status — accounting needs a human. Just log + leave a note.
    factuur = frappe.get_doc("NixFact Factuur", factuur_name)
    note = (
        f"Mollie meldde {status} op {nowdate()}. "
        f"Bedrag: {payment_data.get('amount', {}).get('value', '?')}"
    )
    factuur.opmerkingen = (factuur.opmerkingen or "") + f"\n\n[{nowdate()}] {note}"
    factuur.save(ignore_permissions=True)
    frappe.db.commit()
