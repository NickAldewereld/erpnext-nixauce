# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Auto-numbering engine for NixFact DocTypes.

Supported formats:
    FAC-2026-03-001  (prefix-year-month-seq)
    FAC-2026-001     (prefix-year-seq)
    FAC-001          (prefix-seq)

The next sequence number is derived from the **highest existing number for
the current period** in the actual table, not from a free-running counter
in NixFact Instellingen. This means:

    * Per-year / per-month reset is automatic — when 2027 starts, the next
      number is FAC-2027-001 again.
    * Gaps from failed inserts are tolerated and filled by retries.
    * Backups/restores leave numbering consistent (no drift between settings
      counter and actual rows).

The configured ``*_volgnummer`` field acts as a **start-from minimum** for
fresh installations or freshly-rolled periods that have no rows yet — useful
for migrating in from another system mid-year.

Concurrency: we serialize via ``SELECT … FOR UPDATE`` on the sentinel
singleton row so two concurrent inserts cannot both produce the same number.
"""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

# (prefix_field, counter_field, year_field, month_field, nummer_field)
DOCTYPE_NUMBERING: dict[str, tuple[str, str, str, str, str]] = {
    "NixFact Offerte": (
        "offerte_voorvoegsel",
        "offerte_volgnummer",
        "gebruik_jaar_offerte",
        "gebruik_maand_offerte",
        "offerte_nr",
    ),
    "NixFact Factuur": (
        "factuur_voorvoegsel",
        "factuur_volgnummer",
        "gebruik_jaar_factuur",
        "gebruik_maand_factuur",
        "factuurnummer",
    ),
    "NixFact Inkoopfactuur": (
        "inkoopfactuur_voorvoegsel",
        "inkoopfactuur_volgnummer",
        "gebruik_jaar_inkoopfactuur",
        "gebruik_maand_inkoopfactuur",
        "inkoopfactuur_nr",
    ),
}

_TRAILING_SEQ_RE = re.compile(r"-(\d+)$")


def get_next_nummer(doctype: str) -> str:
    """Generate the next sequential number for a NixFact DocType.

    Atomic across concurrent inserts — see module docstring.
    """
    if doctype not in DOCTYPE_NUMBERING:
        frappe.throw(_("Nummering niet geconfigureerd voor {0}").format(doctype))

    cfg = DOCTYPE_NUMBERING[doctype]
    prefix_field, counter_field, year_field, month_field, _nummer_field = cfg

    settings = frappe.get_single("NixFact Instellingen")
    prefix = (getattr(settings, prefix_field, None) or doctype[:3].upper()).strip()
    use_year = bool(getattr(settings, year_field, False))
    use_month = bool(getattr(settings, month_field, False))
    start_min = int(getattr(settings, counter_field, 1) or 1)

    # Serialize concurrent calls. Locking the singles row that the configured
    # counter lives on is enough — every numbering call goes through here.
    frappe.db.sql(
        """
        SELECT 1 FROM `tabSingles`
        WHERE doctype = %s AND field = %s
        FOR UPDATE
        """,
        ("NixFact Instellingen", counter_field),
    )

    today = getdate(nowdate())
    if use_year and use_month:
        like = f"{prefix}-{today.year}-{today.month:02d}-%"
    elif use_year:
        like = f"{prefix}-{today.year}-%"
    else:
        like = f"{prefix}-%"

    highest = _highest_seq_for_period(doctype, like)
    next_seq = max(highest + 1, start_min)

    nummer = _build_nummer(prefix, next_seq, today, use_year, use_month)
    return nummer


def _highest_seq_for_period(doctype: str, like_pattern: str) -> int:
    """Find the largest trailing sequence among existing rows in this period."""
    rows = frappe.db.sql(
        f"SELECT name FROM `tab{doctype}` WHERE name LIKE %s",
        (like_pattern,),
        as_list=True,
    )
    highest = 0
    for (name,) in rows:
        m = _TRAILING_SEQ_RE.search(name or "")
        if m:
            try:
                v = int(m.group(1))
            except ValueError:
                continue
            if v > highest:
                highest = v
    return highest


def _build_nummer(
    prefix: str, counter: int, today, use_year: bool, use_month: bool
) -> str:
    """Format the number string from parts."""
    parts = [prefix]
    if use_year:
        parts.append(str(today.year))
    if use_month:
        parts.append(f"{today.month:02d}")
    parts.append(f"{counter:03d}")
    return "-".join(parts)


def _format_nummer(prefix: str, counter: int, use_year: bool, use_month: bool) -> str:
    """Public-test-compatible wrapper used by tests/test_numbering.py."""
    return _build_nummer(prefix, counter, getdate(nowdate()), use_year, use_month)


def set_nummer_for_doc(doc, doctype: str) -> None:
    """Set the auto-generated number on a document. Call from autoname()."""
    if doctype not in DOCTYPE_NUMBERING:
        frappe.throw(_("Nummering niet geconfigureerd voor {0}").format(doctype))

    nummer_field = DOCTYPE_NUMBERING[doctype][4]

    # Import-bewust: als er al een nummer staat (bijv. de WeFact-code bij
    # import), behoud dat en genereer geen nieuw nummer.
    bestaand = getattr(doc, nummer_field, None)
    if bestaand:
        doc.name = bestaand
        return

    nummer = get_next_nummer(doctype)
    setattr(doc, nummer_field, nummer)
    doc.name = nummer
