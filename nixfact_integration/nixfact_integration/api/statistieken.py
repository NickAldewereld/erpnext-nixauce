# Copyright (c) 2026, Nick Aldewereld
# License: MIT

import frappe
from frappe import _
from frappe.utils import getdate, get_first_day, get_last_day, add_months, nowdate


@frappe.whitelist()
def get_dashboard_data(periode="maand", jaar=None, maand=None):
	"""
	Get dashboard statistics for a given period.

	Args:
	    periode: 'maand', 'kwartaal', or 'jaar'
	    jaar: Year (default: current)
	    maand: Month (default: current, only used for 'maand' period)

	Returns:
	    dict with totale_omzet, totale_kosten, resultaat, etc.
	"""
	today = getdate(nowdate())
	jaar = int(jaar or today.year)
	maand = int(maand or today.month)

	if periode == "maand":
		from_date = get_first_day(f"{jaar}-{maand:02d}-01")
		to_date = get_last_day(f"{jaar}-{maand:02d}-01")
	elif periode == "kwartaal":
		kwartaal_start = ((maand - 1) // 3) * 3 + 1
		from_date = getdate(f"{jaar}-{kwartaal_start:02d}-01")
		to_date = get_last_day(add_months(from_date, 2))
	else:  # jaar
		from_date = getdate(f"{jaar}-01-01")
		to_date = getdate(f"{jaar}-12-31")

	# Revenue
	omzet_data = frappe.db.sql("""
		SELECT
			COALESCE(SUM(bedrag_incl_btw), 0) as totaal,
			COUNT(*) as aantal
		FROM `tabNixFact Factuur`
		WHERE factuur_datum BETWEEN %s AND %s
		AND status != 'Concept'
	""", (from_date, to_date), as_dict=True)[0]

	totale_omzet = omzet_data.totaal or 0
	aantal_facturen = omzet_data.aantal or 0

	# Costs
	totale_kosten = frappe.db.sql("""
		SELECT COALESCE(SUM(bedrag_incl), 0)
		FROM `tabNixFact Inkoopfactuur`
		WHERE factuurdatum BETWEEN %s AND %s
	""", (from_date, to_date))[0][0] or 0

	# Outstanding
	openstaand_bedrag = frappe.db.sql("""
		SELECT COALESCE(SUM(openstaand_bedrag), 0)
		FROM `tabNixFact Factuur`
		WHERE status IN ('Verstuurd', 'Herinnering verstuurd', 'Aanmaning verstuurd')
	""")[0][0] or 0

	# Monthly chart data (last 12 months)
	grafiek_data = []
	maand_namen = [
		"jan", "feb", "mrt", "apr", "mei", "jun",
		"jul", "aug", "sep", "okt", "nov", "dec",
	]
	for i in range(11, -1, -1):
		m_date = add_months(today, -i)
		m_start = get_first_day(m_date)
		m_end = get_last_day(m_date)

		m_omzet = frappe.db.sql("""
			SELECT COALESCE(SUM(bedrag_incl_btw), 0)
			FROM `tabNixFact Factuur`
			WHERE factuur_datum BETWEEN %s AND %s AND status != 'Concept'
		""", (m_start, m_end))[0][0] or 0

		m_kosten = frappe.db.sql("""
			SELECT COALESCE(SUM(bedrag_incl), 0)
			FROM `tabNixFact Inkoopfactuur`
			WHERE factuurdatum BETWEEN %s AND %s
		""", (m_start, m_end))[0][0] or 0

		grafiek_data.append({
			"maand": maand_namen[getdate(m_start).month - 1],
			"omzet": float(m_omzet),
			"kosten": float(m_kosten),
		})

	# Top customers
	top_klanten = frappe.db.sql("""
		SELECT klant, klant_naam,
			SUM(bedrag_incl_btw) as omzet
		FROM `tabNixFact Factuur`
		WHERE factuur_datum BETWEEN %s AND %s AND status != 'Concept'
		GROUP BY klant, klant_naam
		ORDER BY omzet DESC
		LIMIT 10
	""", (from_date, to_date), as_dict=True)

	return {
		"totale_omzet": float(totale_omzet),
		"totale_kosten": float(totale_kosten),
		"resultaat": float(totale_omzet - totale_kosten),
		"aantal_facturen": aantal_facturen,
		"gemiddelde_factuurwaarde": round(float(totale_omzet / aantal_facturen), 2) if aantal_facturen else 0,
		"openstaand_bedrag": float(openstaand_bedrag),
		"grafiek_data": grafiek_data,
		"top_klanten": top_klanten,
	}


@frappe.whitelist()
def get_btw_overzicht(kwartaal, jaar=None):
	"""
	BTW reporting per quarter.

	Args:
	    kwartaal: 1-4
	    jaar: Year (default: current)

	Returns:
	    dict with verkoop_btw, inkoop_btw, af_te_dragen
	"""
	jaar = int(jaar or getdate(nowdate()).year)
	kwartaal = int(kwartaal)
	start_maand = (kwartaal - 1) * 3 + 1
	from_date = getdate(f"{jaar}-{start_maand:02d}-01")
	to_date = get_last_day(add_months(from_date, 2))

	verkoop_btw = frappe.db.sql("""
		SELECT COALESCE(SUM(btw_bedrag), 0)
		FROM `tabNixFact Factuur`
		WHERE factuur_datum BETWEEN %s AND %s AND status != 'Concept'
	""", (from_date, to_date))[0][0] or 0

	inkoop_btw = frappe.db.sql("""
		SELECT COALESCE(SUM(btw_bedrag), 0)
		FROM `tabNixFact Inkoopfactuur`
		WHERE factuurdatum BETWEEN %s AND %s
	""", (from_date, to_date))[0][0] or 0

	verkoop_excl = frappe.db.sql("""
		SELECT COALESCE(SUM(bedrag_excl_btw), 0)
		FROM `tabNixFact Factuur`
		WHERE factuur_datum BETWEEN %s AND %s AND status != 'Concept'
	""", (from_date, to_date))[0][0] or 0

	inkoop_excl = frappe.db.sql("""
		SELECT COALESCE(SUM(bedrag_excl), 0)
		FROM `tabNixFact Inkoopfactuur`
		WHERE factuurdatum BETWEEN %s AND %s
	""", (from_date, to_date))[0][0] or 0

	return {
		"kwartaal": kwartaal,
		"jaar": jaar,
		"verkoop_excl": float(verkoop_excl),
		"verkoop_btw": float(verkoop_btw),
		"inkoop_excl": float(inkoop_excl),
		"inkoop_btw": float(inkoop_btw),
		"af_te_dragen": float(verkoop_btw - inkoop_btw),
	}


@frappe.whitelist()
def get_omzet_per_klant(jaar=None):
	"""Revenue breakdown by customer for a given year."""
	jaar = int(jaar or getdate(nowdate()).year)
	from_date = getdate(f"{jaar}-01-01")
	to_date = getdate(f"{jaar}-12-31")

	return frappe.db.sql("""
		SELECT
			klant,
			klant_naam,
			COUNT(*) as aantal_facturen,
			SUM(bedrag_excl_btw) as omzet_excl,
			SUM(bedrag_incl_btw) as omzet_incl,
			SUM(btw_bedrag) as btw_totaal
		FROM `tabNixFact Factuur`
		WHERE factuur_datum BETWEEN %s AND %s AND status != 'Concept'
		GROUP BY klant, klant_naam
		ORDER BY omzet_incl DESC
	""", (from_date, to_date), as_dict=True)


@frappe.whitelist()
def get_kosten_per_categorie(jaar=None):
	"""Cost breakdown by category for a given year."""
	jaar = int(jaar or getdate(nowdate()).year)
	from_date = getdate(f"{jaar}-01-01")
	to_date = getdate(f"{jaar}-12-31")

	return frappe.db.sql("""
		SELECT
			COALESCE(kostencategorie, 'Geen categorie') as categorie,
			COUNT(*) as aantal,
			SUM(bedrag_excl) as totaal_excl,
			SUM(bedrag_incl) as totaal_incl
		FROM `tabNixFact Inkoopfactuur`
		WHERE factuurdatum BETWEEN %s AND %s
		GROUP BY kostencategorie
		ORDER BY totaal_incl DESC
	""", (from_date, to_date), as_dict=True)
