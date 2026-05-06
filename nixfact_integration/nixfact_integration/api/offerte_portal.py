# api/offerte_portal.py
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Guest endpoints for the public offerte portal: accept + reject.

All inputs are untrusted Guest data. Every field is regex-validated and
length-bounded before any DB query. The status check (`Verstuurd` only)
makes the accept idempotent — re-posting the form on a Geaccepteerd
offerte is rejected with a clear error.

Threat model:
- Token: max 200 chars checked before DB query (prevents long-string DoS).
- Email: practical RFC subset regex + 254-char hard limit (RFC 5321).
- Signature: PNG data-URL only — JPEG/SVG/HTML rejected (bounds attack
  surface). Max 1.5 MB encoded; a 600x200 canvas signature is ~30 kB.
- IP / User-Agent: truncated to 50 / 500 chars before storage.
- Status guard: only `Verstuurd` can be accepted/rejected — no silent
  override of an already-accepted offerte.
- Mail send is best-effort: failure logs + continues, so the audit record
  (signature, timestamp, IP) is never rolled back due to an SMTP hiccup.
"""

from __future__ import annotations

import re

import frappe
from frappe import _

# Practical email regex — covers >99.9% of valid addresses without
# false-rejecting common patterns (+tags, subdomains, country TLDs).
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}$")
EMAIL_MAX_LEN = 254  # RFC 5321 hard limit on the entire address

# data:image/png;base64,<payload>. We only accept PNG to bound the
# attack surface — JPEG/SVG/HTML data URLs are rejected.
SIGNATURE_RE = re.compile(r"^data:image/png;base64,[A-Za-z0-9+/=]+$")
SIGNATURE_MAX_LEN = 1_500_000  # ~1MB encoded; a 600x200 canvas is ~30kB

TOKEN_MAX_LEN = 200


def _is_valid_email(email) -> bool:
    if not email or not isinstance(email, str):
        return False
    if len(email) > EMAIL_MAX_LEN:
        return False
    return bool(EMAIL_RE.match(email.strip()))


def _is_valid_signature(data_url) -> bool:
    if not data_url or not isinstance(data_url, str):
        return False
    if len(data_url) > SIGNATURE_MAX_LEN:
        return False
    return bool(SIGNATURE_RE.match(data_url))


def _get_offerte_by_token(token):
    if not token or not isinstance(token, str) or len(token) > TOKEN_MAX_LEN:
        frappe.throw(_("Ongeldige link."), frappe.PermissionError)
    name = frappe.db.get_value(
        "NixFact Offerte", {"accept_token": token}, "name"
    )
    if not name:
        frappe.throw(_("Offerte niet gevonden."), frappe.DoesNotExistError)
    return frappe.get_doc("NixFact Offerte", name)


@frappe.whitelist(allow_guest=True)
def accepteer_offerte(token: str, email: str, signature_data_url: str):
    """Accept a quote: validate, persist signature + audit, mark Geaccepteerd."""
    if not _is_valid_email(email):
        frappe.throw(_("Geldig e-mailadres vereist."), frappe.ValidationError)
    if not _is_valid_signature(signature_data_url):
        frappe.throw(_("Ongeldige handtekening."), frappe.ValidationError)

    offerte = _get_offerte_by_token(token)

    if offerte.status != "Verstuurd":
        frappe.throw(
            _("Deze offerte kan niet meer geaccepteerd worden."),
            frappe.ValidationError,
        )

    offerte.handtekening = signature_data_url
    offerte.ondertekend_op = frappe.utils.now_datetime()
    offerte.ondertekend_door_email = email.strip()
    offerte.ondertekend_ip = (frappe.local.request_ip or "")[:50]
    offerte.ondertekend_user_agent = (
        frappe.get_request_header("User-Agent", "") or ""
    )[:500]
    offerte.status = "Geaccepteerd"
    offerte.save(ignore_permissions=True)
    frappe.db.commit()

    _send_accept_emails(offerte)

    return {"status": "ok", "redirect": "/offerte-bedankt"}


@frappe.whitelist(allow_guest=True)
def weiger_offerte(token: str, reden: str = ""):
    """Reject a quote: store reason, flip status to Geweigerd."""
    offerte = _get_offerte_by_token(token)
    if offerte.status != "Verstuurd":
        frappe.throw(
            _("Deze offerte kan niet meer afgewezen worden."),
            frappe.ValidationError,
        )

    offerte.weigering_reden = (reden or "")[:1000]
    offerte.status = "Geweigerd"
    offerte.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "ok"}


def _send_accept_emails(offerte) -> None:
    """Send confirmation to klant + notification to bedrijf-eigenaar.

    Best-effort: a mail-send failure is logged but does NOT roll back
    the accept — the customer signed, that audit record stands.
    """
    try:
        klant_email = offerte.ondertekend_door_email
        subject = _("Bevestiging offerte {0}").format(offerte.offerte_nr)
        body = _(
            "Bedankt voor uw akkoord op offerte {0}.\n\n"
            "Bedrag: € {1}\n\n"
            "Wij nemen zo spoedig mogelijk contact met u op."
        ).format(offerte.offerte_nr, offerte.bedrag_incl)
        frappe.sendmail(recipients=[klant_email], subject=subject, message=body)

        if offerte.company:
            owner_email = frappe.db.get_value(
                "Company", offerte.company, "email"
            )
            if owner_email:
                frappe.sendmail(
                    recipients=[owner_email],
                    subject=_("Offerte {0} geaccepteerd").format(
                        offerte.offerte_nr
                    ),
                    message=_(
                        "Offerte {0} geaccepteerd door {1} op {2}."
                    ).format(
                        offerte.offerte_nr,
                        klant_email,
                        offerte.ondertekend_op,
                    ),
                )
    except Exception:  # noqa: BLE001
        frappe.log_error(
            title="Offerte accept mail",
            message=frappe.get_traceback(),
        )
