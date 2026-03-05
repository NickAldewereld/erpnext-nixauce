# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

import re
from difflib import SequenceMatcher

import frappe
from frappe.utils import nowdate, add_days, getdate


def match_transaction(transaction):
	"""
	Attempt to match a bank transaction to an open invoice.

	Tries strategies in order of confidence:
	  1. Extract invoice number from description/reference (100%)
	  2. Match on amount + customer + date proximity (90-95%)
	  3. Fuzzy name matching (60-80%)

	Args:
	    transaction: NixFact Bank Transactie document or name

	Returns:
	    dict: {factuur: name, confidence: float, methode: str} or None
	"""
	if isinstance(transaction, str):
		transaction = frappe.get_doc("NixFact Bank Transactie", transaction)

	# Only match incoming payments (positive amounts)
	if (transaction.bedrag or 0) <= 0:
		return None

	# Strategy 1: Extract invoice number from text
	result = _match_by_factuurnummer(transaction)
	if result:
		return result

	# Strategy 2: Amount + customer + date proximity
	result = _match_by_bedrag_klant(transaction)
	if result:
		return result

	# Strategy 3: Fuzzy name match
	result = _match_by_naam(transaction)
	if result:
		return result

	return None


def extract_factuurnummer(text):
	"""
	Extract invoice/quote numbers from free text.

	Patterns matched:
	  - FAC-2026-03-001, FAC-2026-001, FAC-001
	  - OFF-2026-03-001, OFF-2026-001, OFF-001
	  - Also without dashes: FAC202603001

	Args:
	    text: String to search

	Returns:
	    str or None: Matched invoice number
	"""
	if not text:
		return None

	patterns = [
		r'(FAC-\d{4}-\d{2}-\d{3,4})',
		r'(FAC-\d{4}-\d{3,4})',
		r'(FAC-\d{3,4})',
		r'(OFF-\d{4}-\d{2}-\d{3,4})',
		r'(OFF-\d{4}-\d{3,4})',
		r'(OFF-\d{3,4})',
	]

	for pattern in patterns:
		match = re.search(pattern, text, re.IGNORECASE)
		if match:
			return match.group(1).upper()

	return None


def string_similarity(a, b):
	"""
	Calculate similarity ratio between two strings.

	Uses SequenceMatcher for fuzzy matching.

	Returns:
	    float: 0.0 to 1.0 similarity score
	"""
	if not a or not b:
		return 0.0
	return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def auto_afletteren(transaction_name, factuur_name):
	"""
	Match a transaction to an invoice: mark invoice as paid, transaction as settled.

	Args:
	    transaction_name: NixFact Bank Transactie name
	    factuur_name: NixFact Factuur name
	"""
	factuur = frappe.get_doc("NixFact Factuur", factuur_name)
	transaction = frappe.get_doc("NixFact Bank Transactie", transaction_name)

	factuur.betaald_bedrag = transaction.bedrag
	factuur.betaaldatum = transaction.datum
	factuur.openstaand_bedrag = (factuur.bedrag_incl_btw or 0) - transaction.bedrag
	if factuur.openstaand_bedrag <= 0:
		factuur.status = "Betaald"
	factuur.save(ignore_permissions=True)

	transaction.status = "Afgeleterd"
	transaction.gekoppeld_aan_type = "NixFact Factuur"
	transaction.gekoppeld_aan = factuur_name
	transaction.save(ignore_permissions=True)


def match_and_settle_all():
	"""
	Run matching on all unprocessed transactions.
	Auto-settles matches with confidence >= 95%.

	Returns:
	    dict: {matched: int, auto_settled: int, unmatched: int}
	"""
	settings = frappe.get_single("NixFact Instellingen")
	if not settings.automatisch_matchen:
		return {"matched": 0, "auto_settled": 0, "unmatched": 0}

	transactions = frappe.get_all(
		"NixFact Bank Transactie",
		filters={"status": "Onverwerkt"},
		fields=["name"],
	)

	matched = 0
	auto_settled = 0
	unmatched = 0

	for txn in transactions:
		result = match_transaction(txn.name)
		if result:
			matched += 1
			doc = frappe.get_doc("NixFact Bank Transactie", txn.name)
			doc.confidence_score = result["confidence"]

			if result["confidence"] >= 95:
				auto_afletteren(txn.name, result["factuur"])
				auto_settled += 1
			else:
				doc.status = "Match gevonden"
				doc.gekoppeld_aan_type = "NixFact Factuur"
				doc.gekoppeld_aan = result["factuur"]
				doc.save(ignore_permissions=True)
		else:
			unmatched += 1

	frappe.db.commit()
	return {"matched": matched, "auto_settled": auto_settled, "unmatched": unmatched}


# --- Private matching strategies ---


def _match_by_factuurnummer(transaction):
	"""Strategy 1: Extract invoice number from description or reference."""
	for text in [transaction.referentie, transaction.omschrijving]:
		nummer = extract_factuurnummer(text)
		if not nummer:
			continue

		factuur = frappe.db.get_value(
			"NixFact Factuur",
			{"factuurnummer": nummer, "status": ["not in", ["Betaald", "Oninbaar"]]},
			"name",
		)
		if factuur:
			return {"factuur": factuur, "confidence": 100.0, "methode": "factuurnummer"}

	return None


def _match_by_bedrag_klant(transaction):
	"""Strategy 2: Match on exact amount + customer + date proximity (±7 days)."""
	if not transaction.bedrag:
		return None

	facturen = frappe.get_all(
		"NixFact Factuur",
		filters={
			"bedrag_incl_btw": transaction.bedrag,
			"status": ["not in", ["Betaald", "Oninbaar"]],
		},
		fields=["name", "klant", "factuurnummer", "vervaldatum"],
	)

	if not facturen:
		return None

	txn_datum = getdate(transaction.datum)
	best_match = None
	best_score = 0

	for f in facturen:
		score = 90.0

		# Bonus for date proximity to due date
		if f.vervaldatum:
			dag_verschil = abs((txn_datum - getdate(f.vervaldatum)).days)
			if dag_verschil <= 3:
				score += 5
			elif dag_verschil <= 7:
				score += 2

		# Bonus for name similarity with customer
		if transaction.naam and f.klant:
			klant_naam = frappe.db.get_value("Customer", f.klant, "customer_name") or ""
			sim = string_similarity(transaction.naam, klant_naam)
			if sim > 0.6:
				score += sim * 5  # up to 5 extra points

		if score > best_score:
			best_score = score
			best_match = f

	if best_match:
		return {
			"factuur": best_match.name,
			"confidence": min(best_score, 99.0),
			"methode": "bedrag_klant",
		}

	return None


def _match_by_naam(transaction):
	"""Strategy 3: Fuzzy match counterparty name against customers with open invoices."""
	if not transaction.naam:
		return None

	# Get customers with open invoices
	open_facturen = frappe.get_all(
		"NixFact Factuur",
		filters={"status": ["not in", ["Betaald", "Oninbaar"]]},
		fields=["name", "klant", "bedrag_incl_btw"],
	)

	best_match = None
	best_score = 0

	for f in open_facturen:
		klant_naam = frappe.db.get_value("Customer", f.klant, "customer_name") or ""
		sim = string_similarity(transaction.naam, klant_naam)

		if sim > 0.6 and sim > best_score:
			best_score = sim
			best_match = f

	if best_match:
		confidence = best_score * 80  # 60-80% range
		return {
			"factuur": best_match.name,
			"confidence": min(confidence, 80.0),
			"methode": "naam_fuzzy",
		}

	return None
