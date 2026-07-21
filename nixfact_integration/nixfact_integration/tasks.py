# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Scheduled tasks for NixFact: reminders, dunning, recurring billing."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, nowdate


def _logger():
    """Lazy logger so importing this module doesn't fail outside Frappe."""
    return frappe.logger("nixfact", allow_site=True)


# --------------------------------------------------------------------------
# Reminder ladder
# --------------------------------------------------------------------------


def verstuur_herinneringen() -> None:
    """Daily: send the first payment reminder for overdue invoices.

    Picks invoices whose ``vervaldatum`` is at least
    ``betalingstermijn_herinnering`` days in the past, and that have not
    yet been reminded. Uses the ``herinnering_1`` email template.
    """
    settings = frappe.get_single("NixFact Instellingen")
    termijn = max(1, int(settings.betalingstermijn_herinnering or 7))
    grens = add_days(nowdate(), -termijn)

    facturen = frappe.get_all(
        "NixFact Factuur",
        filters={
            "vervaldatum": ["<=", grens],
            "herinnering_verstuurd": 0,
            "status": "Verstuurd",
            "openstaand_bedrag": [">", 0],
        },
        fields=["name"],
    )

    sent = 0
    for f in facturen:
        try:
            if _send_reminder(f.name, "herinnering_1", "Herinnering verstuurd"):
                sent += 1
        except Exception:  # noqa: BLE001 — log, don't take down the whole cron
            frappe.log_error(
                title="Herinnering fout",
                message=frappe.get_traceback(),
            )
    frappe.db.commit()
    _logger().info("verstuur_herinneringen: %s verstuurd uit %s kandidaten", sent, len(facturen))


def verstuur_aanmaningen() -> None:
    """Daily: escalate to a formal aanmaning when the reminder went unheeded."""
    settings = frappe.get_single("NixFact Instellingen")
    termijn = max(1, int(settings.betalingstermijn_aanmaning or 7))
    grens = add_days(nowdate(), -termijn)

    facturen = frappe.get_all(
        "NixFact Factuur",
        filters={
            "herinnering_verstuurd": 1,
            "aanmaning_verstuurd": 0,
            "herinnering_datum": ["<=", grens],
            "status": "Herinnering verstuurd",
            "openstaand_bedrag": [">", 0],
        },
        fields=["name"],
    )

    sent = 0
    for f in facturen:
        try:
            if _send_reminder(f.name, "herinnering_2", "Aanmaning verstuurd"):
                sent += 1
        except Exception:  # noqa: BLE001
            frappe.log_error(
                title="Aanmaning fout",
                message=frappe.get_traceback(),
            )
    frappe.db.commit()
    _logger().info("verstuur_aanmaningen: %s verstuurd uit %s kandidaten", sent, len(facturen))


def _send_reminder(factuur_name: str, template: str, new_status: str) -> bool:
    """Send one reminder email and flag the invoice. Idempotent.

    Returns True if email was enqueued and flag updated, False otherwise.
    The send + flag run in the same Frappe DB transaction, so if either
    side fails the row stays untouched and we retry next run.
    """
    factuur = frappe.get_doc("NixFact Factuur", factuur_name)

    # Idempotency: re-check flags inside this transaction (could've been
    # set by a concurrent run).
    if template == "herinnering_1" and factuur.herinnering_verstuurd:
        return False
    if template == "herinnering_2" and factuur.aanmaning_verstuurd:
        return False

    klant_email = frappe.db.get_value("Customer", factuur.klant, "email_id")
    if not klant_email:
        _logger().warning(
            "Klant %s heeft geen email — sla %s voor %s over",
            factuur.klant,
            template,
            factuur.factuurnummer,
        )
        return False

    company_name = (
        factuur.company or frappe.defaults.get_defaults().get("company") or "NixFact"
    )

    subject_prefix = (
        _("Herinnering") if template == "herinnering_1" else _("Aanmaning")
    )
    subject = f"{subject_prefix} factuur {factuur.factuurnummer}"

    frappe.sendmail(
        recipients=[klant_email],
        subject=subject,
        template=template,
        args={
            "doc": factuur,
            "betaallink": factuur.betaallink or "",
            "company_name": company_name,
        },
        delayed=False,
    )

    if template == "herinnering_1":
        factuur.herinnering_verstuurd = 1
        factuur.herinnering_datum = nowdate()
    else:
        factuur.aanmaning_verstuurd = 1
        factuur.aanmaning_datum = nowdate()
    factuur.status = new_status
    factuur.save(ignore_permissions=True)
    return True


# --------------------------------------------------------------------------
# Recurring subscription billing
# --------------------------------------------------------------------------


def _abonnement_regel(abo) -> dict:
    """Map an abonnement (row/doc with attribute access) to one factuurregel.

    Pure function — no frappe calls — so it can be unit-tested against the
    stubbed frappe used by the pytest suite.
    """
    btw_percentage = flt(abo.btw_percentage, 2)
    return {
        "omschrijving": abo.omschrijving or f"Abonnement {abo.name}",
        "aantal": 1,
        "eenheidsprijs": flt(abo.bedrag_excl_btw, 2),
        "btw_categorie": "Standaard" if btw_percentage > 0 else "Nultarief",
        "btw_percentage": btw_percentage,
    }


def genereer_abonnement_facturen() -> None:
    """Generate invoices from active subscriptions whose period is due.

    Each abonnement is processed inside its own savepoint so a single
    failure does not produce a half-completed state (factuur inserted
    but ``volgende_factuur_datum`` not advanced).

    The new factuur is dated ``abo.volgende_factuur_datum`` (not today),
    so an invoice generated `vooraf_dagen` ahead still lands in the
    correct BTW kwartaal.

    Idempotent on (abonnement, factuur_datum) — a transient retry won't
    create a second invoice for the same period.
    """
    settings = frappe.get_single("NixFact Instellingen")
    if not settings.auto_factureren_abonnementen:
        return

    vooraf_dagen = max(0, int(settings.abonnement_vooraf_dagen or 1))
    target_datum = add_days(nowdate(), vooraf_dagen)

    abonnementen = frappe.get_all(
        "NixFact Abonnement",
        filters={
            "status": "Actief",
            "volgende_factuur_datum": ["<=", target_datum],
        },
        fields=[
            "name",
            "klant",
            "omschrijving",
            "bedrag_excl_btw",
            "btw_percentage",
            "frequentie",
            "volgende_factuur_datum",
        ],
    )

    created = 0
    for abo in abonnementen:
        savepoint = f"abo_{abo.name.replace('-', '_')}"
        try:
            frappe.db.savepoint(savepoint)
            volgende = getdate(abo.volgende_factuur_datum)

            # Idempotency: have we already billed this period?
            if frappe.db.exists(
                "NixFact Factuur",
                {"abonnement": abo.name, "factuur_datum": volgende},
            ):
                continue

            factuur = frappe.get_doc(
                {
                    "doctype": "NixFact Factuur",
                    "klant": abo.klant,
                    "factuur_datum": volgende,
                    "referentie": abo.omschrijving,
                    "abonnement": abo.name,
                    "status": "Verstuurd",
                    "regels": [_abonnement_regel(abo)],
                }
            )
            factuur.insert(ignore_permissions=True)

            abo_doc = frappe.get_doc("NixFact Abonnement", abo.name)
            abo_doc.laatste_factuur_datum = volgende
            abo_doc.volgende_factuur_datum = _volgende_datum(volgende, abo.frequentie)
            abo_doc.save(ignore_permissions=True)
            created += 1
        except Exception:  # noqa: BLE001
            frappe.db.rollback(save_point=savepoint)
            frappe.log_error(
                title="Abonnement factuur fout",
                message=frappe.get_traceback(),
            )

    frappe.db.commit()
    _logger().info(
        "genereer_abonnement_facturen: %s facturen gemaakt uit %s kandidaten",
        created,
        len(abonnementen),
    )


def _volgende_datum(huidige_datum, frequentie: str):
    """Calculate next billing date based on frequency."""
    maanden = {
        "Maandelijks": 1,
        "Kwartaal": 3,
        "Halfjaarlijks": 6,
        "Jaarlijks": 12,
    }
    return add_months(huidige_datum, maanden.get(frequentie, 1))
