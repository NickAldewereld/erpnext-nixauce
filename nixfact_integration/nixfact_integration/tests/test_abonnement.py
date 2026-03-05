# Copyright (c) 2026, Nick Aldewereld
# License: MIT

"""Tests for subscription date calculations."""

import unittest
from datetime import date

from nixfact_integration.tasks import _volgende_datum


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


if __name__ == "__main__":
	unittest.main()
