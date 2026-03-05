# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Auto-numbering engine for all NixFact DocTypes.

Supports formats:
  - FAC-2026-03-001  (prefix + year + month + seq)
  - FAC-2026-001     (prefix + year + seq)
  - FAC-001          (prefix + seq)

Counters are stored in the NixFact Instellingen singleton and
incremented atomically via frappe.db.set_single_value.
"""

import frappe
from frappe import _
from frappe.utils import nowdate, getdate

# (prefix_field, counter_field, year_field, month_field, nummer_field)
DOCTYPE_NUMBERING = {
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


def get_next_nummer(doctype):
	"""Generate the next sequential number for a NixFact DocType."""
	if doctype not in DOCTYPE_NUMBERING:
		frappe.throw(_("Nummering niet geconfigureerd voor {0}").format(doctype))

	prefix_field, counter_field, year_field, month_field, _ = DOCTYPE_NUMBERING[doctype]

	settings = frappe.get_single("NixFact Instellingen")
	prefix = getattr(settings, prefix_field) or doctype[:3].upper()
	use_year = getattr(settings, year_field, False)
	use_month = getattr(settings, month_field, False)

	counter = getattr(settings, counter_field) or 1
	nummer = _format_nummer(prefix, counter, use_year, use_month)

	frappe.db.set_single_value("NixFact Instellingen", counter_field, counter + 1)

	return nummer


def _format_nummer(prefix, counter, use_year, use_month):
	"""Build the formatted number string from parts."""
	today = getdate(nowdate())
	parts = [prefix]

	if use_year:
		parts.append(str(today.year))
	if use_month:
		parts.append(f"{today.month:02d}")

	parts.append(f"{counter:03d}")
	return "-".join(parts)


def set_nummer_for_doc(doc, doctype):
	"""Set the auto-generated number on a document. Call from autoname()."""
	if doctype not in DOCTYPE_NUMBERING:
		frappe.throw(_("Nummering niet geconfigureerd voor {0}").format(doctype))

	_, _, _, _, nummer_field = DOCTYPE_NUMBERING[doctype]
	nummer = get_next_nummer(doctype)
	setattr(doc, nummer_field, nummer)
	doc.name = nummer
