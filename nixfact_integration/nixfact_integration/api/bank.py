# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

import frappe
from frappe import _


@frappe.whitelist()
def sync_ponto_transactions(bank_koppeling_id):
	"""
	Sync transactions from Ponto for a given bank koppeling,
	then run the matching engine on new transactions.

	Args:
	    bank_koppeling_id: NixFact Bank Koppeling document name

	Returns:
	    dict: {imported, skipped, matched, auto_settled, unmatched}
	"""
	koppeling = frappe.get_doc("NixFact Bank Koppeling", bank_koppeling_id)

	if not koppeling.actief:
		frappe.throw(_("Deze bankkoppeling is niet actief."))

	if koppeling.koppeling_type != "Ponto":
		frappe.throw(_("Deze functie is alleen beschikbaar voor Ponto koppelingen."))

	# Phase 1: Import transactions
	from nixfact_integration.integrations.ponto import PontoIntegration

	ponto = PontoIntegration(koppeling)
	sync_result = ponto.sync()

	# Phase 2: Run matching on unprocessed transactions
	from nixfact_integration.utils.bank_matching import match_and_settle_all

	match_result = match_and_settle_all()

	return {
		"imported": sync_result["imported"],
		"skipped": sync_result["skipped"],
		"matched": match_result["matched"],
		"auto_settled": match_result["auto_settled"],
		"unmatched": match_result["unmatched"],
	}
