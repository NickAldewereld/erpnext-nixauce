# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests for subscription date calculations."""

import unittest
import types
from datetime import date

from nixfact_integration.tasks import (
	_abonnement_regel,
	_mislukking_reden,
	_vat_mislukkingen,
	_volgende_datum,
)


class TestVolgendeDatum(unittest.TestCase):
	"""Test next billing date calculation for all frequencies."""

	def test_maandelijks(self):
		result = _volgende_datum(date(2026, 1, 15), "Maandelijks")
		self.assertEqual(result, date(2026, 2, 15))

	def test_kwartaal(self):
		result = _volgende_datum(date(2026, 1, 1), "Kwartaal")
		self.assertEqual(result, date(2026, 4, 1))

	def test_halfjaarlijks(self):
		result = _volgende_datum(date(2026, 3, 1), "Halfjaarlijks")
		self.assertEqual(result, date(2026, 9, 1))

	def test_jaarlijks(self):
		result = _volgende_datum(date(2026, 6, 15), "Jaarlijks")
		self.assertEqual(result, date(2027, 6, 15))

	def test_month_end_handling(self):
		# Jan 31 + 1 month should not crash
		result = _volgende_datum(date(2026, 1, 31), "Maandelijks")
		# frappe.utils.add_months handles month-end gracefully
		self.assertIsNotNone(result)

	def test_unknown_frequency_defaults_monthly(self):
		result = _volgende_datum(date(2026, 1, 1), "Onbekend")
		self.assertEqual(result, date(2026, 2, 1))


class TestAbonnementRegel(unittest.TestCase):
	"""Test mapping an abonnement to a single NixFact Factuur Regel dict."""

	def _abo(self, **overrides):
		defaults = dict(
			name="ABO-0001",
			omschrijving="Hosting pakket",
			bedrag_excl_btw=100.0,
			btw_percentage=21,
		)
		defaults.update(overrides)
		return types.SimpleNamespace(**defaults)

	def test_standaard_tarief(self):
		regel = _abonnement_regel(self._abo())
		self.assertEqual(regel["btw_categorie"], "Standaard")
		self.assertEqual(regel["eenheidsprijs"], 100.0)
		self.assertEqual(regel["aantal"], 1)
		self.assertEqual(regel["omschrijving"], "Hosting pakket")
		self.assertEqual(regel["btw_percentage"], 21)

	def test_nultarief(self):
		regel = _abonnement_regel(self._abo(btw_percentage=0))
		self.assertEqual(regel["btw_categorie"], "Nultarief")

	def test_lege_omschrijving_valt_terug_op_naam(self):
		regel = _abonnement_regel(self._abo(omschrijving="", name="ABO-0042"))
		self.assertEqual(regel["omschrijving"], "Abonnement ABO-0042")


class TestMislukkingMelding(unittest.TestCase):
	"""Test failure-visibility helpers for the abonnement-facturen cron."""

	def test_mislukking_reden_strips_html(self):
		exc = Exception(
			"Deze factuur voldoet nog niet aan de e-facturatie-eisen:"
			"<ul><li>Het land van de klant ontbreekt in het adres.</li></ul>"
		)
		reden = _mislukking_reden(exc)
		self.assertIn("Het land van de klant ontbreekt", reden)
		self.assertNotIn("<", reden)
		self.assertNotIn(">", reden)

	def test_mislukking_reden_plain_exception(self):
		reden = _mislukking_reden(ValueError("iets kapot"))
		self.assertEqual(reden, "iets kapot")

	def test_vat_mislukkingen_bevat_alle_regels(self):
		mislukt = [
			{"abonnement": "ABO-0001", "klant": "Klant A", "reden": "reden een"},
			{"abonnement": "ABO-0002", "klant": "Klant B", "reden": "reden twee"},
		]
		samenvatting = _vat_mislukkingen(mislukt)
		self.assertIn("ABO-0001", samenvatting)
		self.assertIn("ABO-0002", samenvatting)
		self.assertIn("Klant A", samenvatting)
		self.assertIn("Klant B", samenvatting)
		self.assertIn("2", samenvatting)

	def test_vat_mislukkingen_lege_lijst(self):
		samenvatting = _vat_mislukkingen([])
		self.assertEqual(samenvatting, "0 abonnement(en) niet gefactureerd:")


if __name__ == "__main__":
	unittest.main()
