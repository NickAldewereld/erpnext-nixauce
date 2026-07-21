# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests for subscription date calculations."""

import unittest
import types
from datetime import date

from nixfact_integration.tasks import _abonnement_regel, _volgende_datum


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


if __name__ == "__main__":
	unittest.main()
