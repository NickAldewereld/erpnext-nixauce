# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

import frappe
from frappe.utils import nowdate, add_days, add_months, getdate


def verstuur_herinneringen():
	"""Daily: Send payment reminders for overdue invoices."""
	settings = frappe.get_single("NixFact Instellingen")
	termijn = settings.betalingstermijn_herinnering or 7
	max_herinneringen = settings.aantal_herinneringen or 1

	# Find overdue, unpaid invoices that haven't received a reminder yet
	grens_datum = add_days(nowdate(), -termijn)
	facturen = frappe.get_all(
		"NixFact Factuur",
		filters={
			"status": "Verstuurd",
			"vervaldatum": ["<=", grens_datum],
			"herinnering_verstuurd": 0,
		},
		fields=["name", "klant", "factuurnummer", "bedrag_incl_btw", "vervaldatum"],
	)

	for f in facturen:
		try:
			doc = frappe.get_doc("NixFact Factuur", f.name)
			doc.herinnering_verstuurd = 1
			doc.herinnering_datum = nowdate()
			doc.status = "Herinnering verstuurd"
			doc.save(ignore_permissions=True)

			frappe.log_error(
				title="Herinnering verstuurd",
				message=f"Herinnering verstuurd voor {f.factuurnummer} aan {f.klant}",
			)
		except Exception:
			frappe.log_error(
				title="Herinnering fout",
				message=f"Fout bij versturen herinnering voor {f.factuurnummer}",
			)

	frappe.db.commit()


def verstuur_aanmaningen():
	"""Daily: Send payment summons for invoices still unpaid after reminder."""
	settings = frappe.get_single("NixFact Instellingen")
	termijn = settings.betalingstermijn_aanmaning or 7

	# Find invoices where reminder was sent but still unpaid
	grens_datum = add_days(nowdate(), -termijn)
	facturen = frappe.get_all(
		"NixFact Factuur",
		filters={
			"status": "Herinnering verstuurd",
			"herinnering_datum": ["<=", grens_datum],
			"aanmaning_verstuurd": 0,
		},
		fields=["name", "klant", "factuurnummer"],
	)

	for f in facturen:
		try:
			doc = frappe.get_doc("NixFact Factuur", f.name)
			doc.aanmaning_verstuurd = 1
			doc.aanmaning_datum = nowdate()
			doc.status = "Aanmaning verstuurd"
			doc.save(ignore_permissions=True)

			frappe.log_error(
				title="Aanmaning verstuurd",
				message=f"Aanmaning verstuurd voor {f.factuurnummer} aan {f.klant}",
			)
		except Exception:
			frappe.log_error(
				title="Aanmaning fout",
				message=f"Fout bij versturen aanmaning voor {f.factuurnummer}",
			)

	frappe.db.commit()


def genereer_abonnement_facturen():
	"""09:00 daily: Generate invoices from active subscriptions."""
	settings = frappe.get_single("NixFact Instellingen")

	if not settings.auto_factureren_abonnementen:
		return

	vooraf_dagen = settings.abonnement_vooraf_dagen or 1
	target_datum = add_days(nowdate(), vooraf_dagen)

	abonnementen = frappe.get_all(
		"NixFact Abonnement",
		filters={
			"status": "Actief",
			"volgende_factuur_datum": ["<=", target_datum],
		},
		fields=[
			"name", "klant", "omschrijving", "bedrag_excl_btw",
			"btw_percentage", "frequentie", "volgende_factuur_datum",
		],
	)

	for abo in abonnementen:
		try:
			factuur = frappe.get_doc({
				"doctype": "NixFact Factuur",
				"klant": abo.klant,
				"factuur_datum": nowdate(),
				"bedrag_excl_btw": abo.bedrag_excl_btw,
				"btw_percentage": abo.btw_percentage,
				"referentie": abo.omschrijving,
				"abonnement": abo.name,
				"status": "Verstuurd",
			})
			factuur.insert(ignore_permissions=True)

			# Advance the subscription to next billing date
			abo_doc = frappe.get_doc("NixFact Abonnement", abo.name)
			abo_doc.laatste_factuur_datum = nowdate()
			abo_doc.volgende_factuur_datum = _volgende_datum(
				getdate(abo.volgende_factuur_datum), abo.frequentie
			)
			abo_doc.save(ignore_permissions=True)

		except Exception:
			frappe.log_error(
				title="Abonnement factuur fout",
				message=f"Fout bij genereren factuur voor abonnement {abo.name}",
			)

	frappe.db.commit()


def _volgende_datum(huidige_datum, frequentie):
	"""Calculate next billing date based on frequency."""
	maanden = {
		"Maandelijks": 1,
		"Kwartaal": 3,
		"Halfjaarlijks": 6,
		"Jaarlijks": 12,
	}
	return add_months(huidige_datum, maanden.get(frequentie, 1))
