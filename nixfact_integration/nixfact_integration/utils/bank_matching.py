# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Bank-transaction-to-invoice matching engine.

Three strategies in order of confidence:

  1. **Factuurnummer mention** in description/reference (100%) — but only
     auto-settles when the matched invoice's customer also matches the
     transaction's IBAN tegenpartij or counterparty name. Without the
     cross-check, a typo'd factuurnummer would silently settle the wrong
     invoice.
  2. **Amount + customer + date proximity** (90-99%). Customer is derived
     from the IBAN (when known) or a fuzzy name match. We refuse to match
     if more than one invoice is a candidate — the human reconciles.
  3. **Fuzzy counterparty name** (60-80%) for review only — never auto-settled.

Money safety:
  * ``auto_afletteren`` *adds* the payment to ``betaald_bedrag`` rather than
    overwriting it, so partial payments accumulate correctly.
  * The factuur row is locked (``for_update``) before mutation, blocking
    a concurrent Mollie webhook from double-settling.
  * Already-settled transactions are skipped (idempotent).
  * All currency arithmetic goes through ``flt(..., 2)``.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

import frappe
from frappe.utils import flt, getdate

# Open invoice statuses that can still receive a payment.
OPEN_STATUSES = ("Concept", "Verstuurd", "Herinnering verstuurd", "Aanmaning verstuurd")

# Confidence ladder.
CONF_FACTUURNUMMER_EXACT = 100.0
CONF_FACTUURNUMMER_NO_CROSSCHECK = 90.0  # mention found, customer not verified
CONF_BEDRAG_KLANT_BASE = 90.0
CONF_NAAM_FUZZY_MAX = 80.0
AUTO_SETTLE_THRESHOLD = 95.0

# Matching tolerance for currency comparison.
AMOUNT_TOLERANCE = 0.01

# Fuzzy match thresholds.
NAAM_MIN_SIM = 0.6


def match_transaction(transaction: Any) -> dict | None:
    """Attempt to match a bank transaction to an open invoice.

    Returns a dict ``{factuur, confidence, methode}`` or ``None``.
    """
    if isinstance(transaction, str):
        transaction = frappe.get_doc("NixFact Bank Transactie", transaction)

    # Idempotency: a transaction already settled in a previous run shouldn't
    # be re-processed at all.
    if (transaction.status or "Onverwerkt") == "Afgeleterd":
        return None

    # Only match incoming payments (positive amounts).
    if flt(transaction.bedrag, 2) <= 0:
        return None

    for strategy in (_match_by_factuurnummer, _match_by_bedrag_klant, _match_by_naam):
        result = strategy(transaction)
        if result:
            return result
    return None


def extract_factuurnummer(text: str | None) -> str | None:
    """Extract a NixFact-format invoice/quote number from free text."""
    if not text:
        return None
    patterns = (
        r"(FAC-\d{4}-\d{2}-\d{3,4})",
        r"(FAC-\d{4}-\d{3,4})",
        r"(FAC-\d{3,4})",
        r"(OFF-\d{4}-\d{2}-\d{3,4})",
        r"(OFF-\d{4}-\d{3,4})",
        r"(OFF-\d{3,4})",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


def string_similarity(a: str | None, b: str | None) -> float:
    """SequenceMatcher ratio, normalized to lowercase + stripped."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def auto_afletteren(transaction_name: str, factuur_name: str, confidence: float) -> None:
    """Apply a settled match: add the payment, mark transaction settled.

    Locks the factuur row before mutation. Idempotent — a transaction that
    is already ``Afgeleterd`` returns immediately.
    """
    txn_status = frappe.db.get_value(
        "NixFact Bank Transactie",
        transaction_name,
        "status",
        for_update=True,
    )
    if txn_status == "Afgeleterd":
        return

    # Lock the factuur row to serialize against a Mollie webhook.
    factuur_row = frappe.db.get_value(
        "NixFact Factuur",
        factuur_name,
        ["bedrag_incl_btw", "betaald_bedrag", "status", "betaaldatum"],
        for_update=True,
        as_dict=True,
    )
    if not factuur_row:
        return

    transaction = frappe.get_doc("NixFact Bank Transactie", transaction_name)

    bedrag = flt(transaction.bedrag, 2)
    huidig_betaald = flt(factuur_row.betaald_bedrag, 2)
    nieuw_betaald = flt(huidig_betaald + bedrag, 2)
    bedrag_incl = flt(factuur_row.bedrag_incl_btw, 2)
    nieuw_openstaand = flt(bedrag_incl - nieuw_betaald, 2)

    factuur = frappe.get_doc("NixFact Factuur", factuur_name)
    factuur.betaald_bedrag = nieuw_betaald
    factuur.betaaldatum = transaction.datum
    factuur.openstaand_bedrag = nieuw_openstaand
    if nieuw_openstaand <= AMOUNT_TOLERANCE:
        factuur.status = "Betaald"
        factuur.openstaand_bedrag = 0
    factuur.save(ignore_permissions=True)

    transaction.status = "Afgeleterd"
    transaction.gekoppeld_aan_type = "NixFact Factuur"
    transaction.gekoppeld_aan = factuur_name
    transaction.confidence_score = confidence
    transaction.save(ignore_permissions=True)


def match_and_settle_all() -> dict[str, int]:
    """Run matching on all unprocessed transactions.

    Auto-settles matches with confidence ≥ AUTO_SETTLE_THRESHOLD; lower
    matches are flagged for human review. Returns counts.
    """
    settings = frappe.get_single("NixFact Instellingen")
    if not settings.automatisch_matchen:
        return {"matched": 0, "auto_settled": 0, "unmatched": 0}

    transactions = frappe.get_all(
        "NixFact Bank Transactie",
        filters={"status": "Onverwerkt"},
        fields=["name"],
        order_by="datum asc",  # apply oldest payments first
    )

    matched = auto_settled = unmatched = 0
    settled_in_run: set[str] = set()

    for txn in transactions:
        result = match_transaction(txn.name)
        if not result:
            unmatched += 1
            continue

        # Don't settle the same factuur twice in one run unless it can take
        # multiple partial payments — for simplicity we skip if it was just
        # marked fully Betaald in this batch.
        if result["factuur"] in settled_in_run:
            unmatched += 1
            continue

        matched += 1
        if result["confidence"] >= AUTO_SETTLE_THRESHOLD:
            auto_afletteren(txn.name, result["factuur"], result["confidence"])
            # Re-check: did this complete the invoice?
            new_status = frappe.db.get_value("NixFact Factuur", result["factuur"], "status")
            if new_status == "Betaald":
                settled_in_run.add(result["factuur"])
            auto_settled += 1
        else:
            doc = frappe.get_doc("NixFact Bank Transactie", txn.name)
            doc.confidence_score = result["confidence"]
            doc.status = "Match gevonden"
            doc.gekoppeld_aan_type = "NixFact Factuur"
            doc.gekoppeld_aan = result["factuur"]
            doc.save(ignore_permissions=True)

    frappe.db.commit()
    return {"matched": matched, "auto_settled": auto_settled, "unmatched": unmatched}


# --------------------------------------------------------------------------
# Private matching strategies
# --------------------------------------------------------------------------


def _match_by_factuurnummer(transaction: Any) -> dict | None:
    """Strategy 1: factuurnummer mention + cross-check on klant.

    Auto-settle confidence (100) requires the matched factuur's klant to
    also match the transaction's IBAN tegenpartij or counterparty name.
    Without that cross-check we return 90 — a typo could otherwise settle
    a totally unrelated invoice.
    """
    haystack = " ".join(
        s
        for s in (transaction.referentie, transaction.omschrijving, transaction.naam)
        if s
    )
    nummer = extract_factuurnummer(haystack)
    if not nummer:
        return None

    factuur = frappe.db.get_value(
        "NixFact Factuur",
        {"factuurnummer": nummer, "status": ["in", OPEN_STATUSES]},
        ["name", "klant"],
        as_dict=True,
    )
    if not factuur:
        return None

    crosscheck_ok = _customer_matches_transaction(factuur.klant, transaction)
    confidence = (
        CONF_FACTUURNUMMER_EXACT if crosscheck_ok else CONF_FACTUURNUMMER_NO_CROSSCHECK
    )
    return {"factuur": factuur.name, "confidence": confidence, "methode": "factuurnummer"}


def _match_by_bedrag_klant(transaction: Any) -> dict | None:
    """Strategy 2: customer-scoped amount + date match.

    Customer is derived from the IBAN (when we have one in Customer's
    bank accounts) or via fuzzy name match above NAAM_MIN_SIM. If we
    cannot identify a customer, this strategy abstains.
    """
    bedrag = flt(transaction.bedrag, 2)
    if bedrag <= 0:
        return None

    klanten = _candidate_customers(transaction)
    if not klanten:
        return None

    facturen = frappe.get_all(
        "NixFact Factuur",
        filters={
            "klant": ["in", list(klanten)],
            "bedrag_incl_btw": ["between", [bedrag - AMOUNT_TOLERANCE, bedrag + AMOUNT_TOLERANCE]],
            "status": ["in", OPEN_STATUSES],
        },
        fields=["name", "klant", "factuurnummer", "vervaldatum"],
    )
    if not facturen:
        return None

    # Refuse to settle if more than one candidate at this amount — human picks.
    if len(facturen) > 1:
        return None

    f = facturen[0]
    score = CONF_BEDRAG_KLANT_BASE
    txn_datum = getdate(transaction.datum)
    if f.vervaldatum:
        diff = abs((txn_datum - getdate(f.vervaldatum)).days)
        if diff <= 3:
            score += 5
        elif diff <= 7:
            score += 2

    if transaction.naam and f.klant:
        klant_naam = (
            frappe.db.get_value("Customer", f.klant, "customer_name") or ""
        )
        sim = string_similarity(transaction.naam, klant_naam)
        if sim > NAAM_MIN_SIM:
            score += sim * 5

    return {
        "factuur": f.name,
        "confidence": min(score, 99.0),
        "methode": "bedrag_klant",
    }


def _match_by_naam(transaction: Any) -> dict | None:
    """Strategy 3: fuzzy counterparty-name match (review only, never auto)."""
    if not transaction.naam:
        return None

    open_facturen = frappe.get_all(
        "NixFact Factuur",
        filters={"status": ["in", OPEN_STATUSES]},
        fields=["name", "klant"],
    )

    best = None
    best_sim = 0.0
    for f in open_facturen:
        klant_naam = frappe.db.get_value("Customer", f.klant, "customer_name") or ""
        sim = string_similarity(transaction.naam, klant_naam)
        if sim > NAAM_MIN_SIM and sim > best_sim:
            best_sim = sim
            best = f

    if not best:
        return None

    return {
        "factuur": best.name,
        "confidence": min(best_sim * CONF_NAAM_FUZZY_MAX, CONF_NAAM_FUZZY_MAX),
        "methode": "naam_fuzzy",
    }


# --------------------------------------------------------------------------
# Customer identification helpers
# --------------------------------------------------------------------------


def _customer_matches_transaction(klant: str | None, transaction: Any) -> bool:
    """True if `klant` is consistent with the transaction's counterparty.

    Considered consistent if either:
      * The transaction's IBAN is on a Bank Account linked to this customer.
      * The transaction's counterparty name is fuzzy-similar (>= 0.7) to
        the customer's customer_name.
    """
    if not klant:
        return False

    iban = (transaction.van_naar or "").replace(" ", "").upper()
    if iban and _customer_owns_iban(klant, iban):
        return True

    if transaction.naam:
        klant_naam = frappe.db.get_value("Customer", klant, "customer_name") or ""
        if string_similarity(transaction.naam, klant_naam) >= 0.7:
            return True

    return False


def _candidate_customers(transaction: Any) -> set[str]:
    """Resolve transaction → set of Customer names.

    Tries IBAN first (high confidence), then fuzzy name match (medium).
    Returns the empty set when neither yields anything actionable.
    """
    iban = (transaction.van_naar or "").replace(" ", "").upper()
    if iban:
        owners = _customers_for_iban(iban)
        if owners:
            return owners

    if not transaction.naam:
        return set()

    # Fall back: fuzzy match against all customer names. We accept a
    # narrow set (any with similarity ≥ 0.8) to keep candidate count low.
    customers = frappe.get_all(
        "Customer",
        fields=["name", "customer_name"],
        limit_page_length=0,
    )
    candidates: set[str] = set()
    for c in customers:
        if string_similarity(transaction.naam, c.customer_name or "") >= 0.8:
            candidates.add(c.name)
    return candidates


def _customers_for_iban(iban: str) -> set[str]:
    """All Customers that own this IBAN via ERPNext Bank Account."""
    rows = frappe.db.sql(
        """
        SELECT DISTINCT party
        FROM `tabBank Account`
        WHERE party_type = 'Customer'
          AND iban IS NOT NULL
          AND REPLACE(UPPER(iban), ' ', '') = %s
        """,
        (iban,),
        as_list=True,
    )
    return {row[0] for row in rows if row[0]}


def _customer_owns_iban(klant: str, iban: str) -> bool:
    """True if `klant` has a Bank Account with this IBAN."""
    return bool(
        frappe.db.sql(
            """
            SELECT 1 FROM `tabBank Account`
            WHERE party_type = 'Customer'
              AND party = %s
              AND iban IS NOT NULL
              AND REPLACE(UPPER(iban), ' ', '') = %s
            LIMIT 1
            """,
            (klant, iban),
            as_list=True,
        )
    )
