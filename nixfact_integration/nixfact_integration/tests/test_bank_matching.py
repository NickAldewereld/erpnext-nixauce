# Copyright (c) 2026, Nick Aldewereld
# License: MIT

"""Tests for the bank transaction matching engine."""

import unittest

from nixfact_integration.utils.bank_matching import (
	extract_factuurnummer,
	string_similarity,
)


class TestExtractFactuurnummer(unittest.TestCase):
	"""Test invoice number extraction from free text."""

	def test_full_format(self):
		self.assertEqual(
			extract_factuurnummer("Betaling FAC-2026-03-001 ontvangen"),
			"FAC-2026-03-001",
		)

	def test_year_only_format(self):
		self.assertEqual(
			extract_factuurnummer("ref FAC-2026-042"),
			"FAC-2026-042",
		)

	def test_simple_format(self):
		self.assertEqual(
			extract_factuurnummer("FAC-001"),
			"FAC-001",
		)

	def test_offerte_number(self):
		self.assertEqual(
			extract_factuurnummer("Betreft OFF-2026-01-005"),
			"OFF-2026-01-005",
		)

	def test_case_insensitive(self):
		result = extract_factuurnummer("betaling fac-2026-03-001")
		self.assertEqual(result, "FAC-2026-03-001")

	def test_no_match(self):
		self.assertIsNone(extract_factuurnummer("Gewone betaling"))

	def test_empty_string(self):
		self.assertIsNone(extract_factuurnummer(""))

	def test_none_input(self):
		self.assertIsNone(extract_factuurnummer(None))

	def test_number_in_longer_text(self):
		text = "Betaling voor factuur FAC-2026-03-007, met dank."
		self.assertEqual(extract_factuurnummer(text), "FAC-2026-03-007")

	def test_four_digit_sequence(self):
		self.assertEqual(
			extract_factuurnummer("FAC-2026-03-1234"),
			"FAC-2026-03-1234",
		)


class TestStringSimilarity(unittest.TestCase):
	"""Test fuzzy string matching."""

	def test_identical(self):
		self.assertAlmostEqual(string_similarity("ACME BV", "ACME BV"), 1.0)

	def test_case_insensitive(self):
		self.assertAlmostEqual(string_similarity("acme bv", "ACME BV"), 1.0)

	def test_similar(self):
		score = string_similarity("J. de Vries", "Jan de Vries")
		self.assertGreater(score, 0.7)

	def test_different(self):
		score = string_similarity("ACME BV", "Bakkerij Jansen")
		self.assertLess(score, 0.4)

	def test_empty_strings(self):
		self.assertEqual(string_similarity("", "something"), 0.0)
		self.assertEqual(string_similarity("something", ""), 0.0)

	def test_none_input(self):
		self.assertEqual(string_similarity(None, "test"), 0.0)
		self.assertEqual(string_similarity("test", None), 0.0)

	def test_whitespace_handling(self):
		score = string_similarity("  ACME BV  ", "ACME BV")
		self.assertAlmostEqual(score, 1.0)


if __name__ == "__main__":
	unittest.main()
