# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests for the auto-numbering engine."""

import unittest
from unittest.mock import patch

from nixfact_integration.utils.numbering import _format_nummer, DOCTYPE_NUMBERING


class TestFormatNummer(unittest.TestCase):
	"""Test number formatting without database dependency."""

	def test_simple_format(self):
		result = _format_nummer("FAC", 1, use_year=False, use_month=False)
		self.assertEqual(result, "FAC-001")

	def test_simple_high_counter(self):
		result = _format_nummer("FAC", 999, use_year=False, use_month=False)
		self.assertEqual(result, "FAC-999")

	def test_four_digit_counter(self):
		result = _format_nummer("FAC", 1234, use_year=False, use_month=False)
		self.assertEqual(result, "FAC-1234")

	@patch("nixfact_integration.utils.numbering.getdate")
	@patch("nixfact_integration.utils.numbering.nowdate")
	def test_year_format(self, mock_nowdate, mock_getdate):
		from datetime import date
		mock_nowdate.return_value = "2026-03-15"
		mock_getdate.return_value = date(2026, 3, 15)
		result = _format_nummer("FAC", 1, use_year=True, use_month=False)
		self.assertEqual(result, "FAC-2026-001")

	@patch("nixfact_integration.utils.numbering.getdate")
	@patch("nixfact_integration.utils.numbering.nowdate")
	def test_year_month_format(self, mock_nowdate, mock_getdate):
		from datetime import date
		mock_nowdate.return_value = "2026-03-15"
		mock_getdate.return_value = date(2026, 3, 15)
		result = _format_nummer("FAC", 1, use_year=True, use_month=True)
		self.assertEqual(result, "FAC-2026-03-001")

	@patch("nixfact_integration.utils.numbering.getdate")
	@patch("nixfact_integration.utils.numbering.nowdate")
	def test_month_padding(self, mock_nowdate, mock_getdate):
		from datetime import date
		mock_nowdate.return_value = "2026-01-05"
		mock_getdate.return_value = date(2026, 1, 5)
		result = _format_nummer("OFF", 42, use_year=True, use_month=True)
		self.assertEqual(result, "OFF-2026-01-042")

	def test_custom_prefix(self):
		result = _format_nummer("INK", 7, use_year=False, use_month=False)
		self.assertEqual(result, "INK-007")


class TestDoctypeNumberingConfig(unittest.TestCase):
	"""Verify the DOCTYPE_NUMBERING registry is correctly configured."""

	def test_offerte_registered(self):
		self.assertIn("NixFact Offerte", DOCTYPE_NUMBERING)

	def test_factuur_registered(self):
		self.assertIn("NixFact Factuur", DOCTYPE_NUMBERING)

	def test_inkoopfactuur_registered(self):
		self.assertIn("NixFact Inkoopfactuur", DOCTYPE_NUMBERING)

	def test_all_tuples_have_5_elements(self):
		for doctype, config in DOCTYPE_NUMBERING.items():
			self.assertEqual(len(config), 5, f"{doctype} config should have 5 elements")


if __name__ == "__main__":
	unittest.main()
