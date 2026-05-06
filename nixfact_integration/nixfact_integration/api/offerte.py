# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Whitelisted endpoints for NixFact Offerte.

These run as the calling user; permissions on the NixFact Offerte DocType
are enforced by Frappe (we do NOT pass ignore_permissions). A caller
without write access to the doctype gets a frappe.PermissionError.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

VALID_STATUSES = (
    "Concept",
    "Verstuurd",
    "Geaccepteerd",
    "Geweigerd",
    "Verlopen",
    "Factuur aangemaakt",
)

REQUIRED_FIELDS = (
    "offerte_nr",
    "klant",
    "bedrag_excl",
    "bedrag_incl",
    "offerte_datum",
)


def _validate_required(offerte_data: dict[str, Any]) -> None:
    """Reject empty or missing required fields. Does not leak field values."""
    if not isinstance(offerte_data, dict):
        frappe.throw(_("offerte_data must be an object."), frappe.ValidationError)

    missing = [f for f in REQUIRED_FIELDS if not offerte_data.get(f)]
    if missing:
        frappe.throw(
            _("Required fields are missing: {0}").format(", ".join(missing)),
            frappe.ValidationError,
        )


@frappe.whitelist()
def create_offerte(offerte_data: dict[str, Any]) -> dict[str, Any]:
    """Create a new NixFact Offerte.

    Args:
        offerte_data: dict with `offerte_nr`, `klant`, `bedrag_excl`,
            `bedrag_incl`, `offerte_datum`, and optional `referentie` /
            `status`. Status defaults to ``Concept``; if provided, must
            be one of ``VALID_STATUSES``.

    Returns:
        dict with ``offerte_id`` (Frappe document name) and ``offerte_nr``.

    Raises:
        frappe.PermissionError: caller lacks create permission on the
            NixFact Offerte doctype.
        frappe.ValidationError: required fields missing or status invalid.
    """
    _validate_required(offerte_data)

    status = offerte_data.get("status") or "Concept"
    if status not in VALID_STATUSES:
        frappe.throw(
            _("Invalid status. Must be one of: {0}").format(", ".join(VALID_STATUSES)),
            frappe.ValidationError,
        )

    offerte = frappe.get_doc(
        {
            "doctype": "NixFact Offerte",
            "offerte_nr": offerte_data["offerte_nr"],
            "klant": offerte_data["klant"],
            "bedrag_excl": offerte_data["bedrag_excl"],
            "bedrag_incl": offerte_data["bedrag_incl"],
            "offerte_datum": offerte_data["offerte_datum"],
            "referentie": offerte_data.get("referentie", ""),
            "status": status,
        }
    )
    offerte.insert()  # respects DocType permissions

    return {
        "success": True,
        "offerte_id": offerte.name,
        "offerte_nr": offerte.offerte_nr,
    }


@frappe.whitelist()
def get_offerte(offerte_id: str) -> dict[str, Any]:
    """Fetch a NixFact Offerte by document name.

    Permission to read is enforced by ``frappe.get_doc``.
    """
    offerte = frappe.get_doc("NixFact Offerte", offerte_id)
    return {
        "success": True,
        "data": {
            "offerte_id": offerte.name,
            "offerte_nr": offerte.offerte_nr,
            "klant": offerte.klant,
            "bedrag_excl": offerte.bedrag_excl,
            "bedrag_incl": offerte.bedrag_incl,
            "offerte_datum": offerte.offerte_datum,
            "referentie": offerte.referentie,
            "status": offerte.status,
            "creation": offerte.creation,
            "modified": offerte.modified,
        },
    }


@frappe.whitelist()
def update_offerte_status(offerte_id: str, status: str) -> dict[str, Any]:
    """Update the status of a NixFact Offerte.

    Permission to write is enforced by ``offerte.save()``.
    """
    if status not in VALID_STATUSES:
        frappe.throw(
            _("Invalid status. Must be one of: {0}").format(", ".join(VALID_STATUSES)),
            frappe.ValidationError,
        )

    offerte = frappe.get_doc("NixFact Offerte", offerte_id)
    offerte.status = status
    offerte.save()

    return {
        "success": True,
        "offerte_id": offerte.name,
        "new_status": offerte.status,
    }
