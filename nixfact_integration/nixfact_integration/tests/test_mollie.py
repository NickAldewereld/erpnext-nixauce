# Copyright (c) 2026, Nick Aldewereld
# License: MIT

"""Tests for Mollie payment integration."""

import unittest
from unittest.mock import patch, MagicMock

from nixfact_integration.integrations.mollie import PAYMENT_ID_PATTERN


class TestPaymentIdValidation(unittest.TestCase):
	"""Test the Mollie payment ID regex pattern."""

	def test_valid_id(self):
		self.assertTrue(PAYMENT_ID_PATTERN.match("tr_abc123"))

	def test_valid_id_long(self):
		self.assertTrue(PAYMENT_ID_PATTERN.match("tr_WDqYoSqBm9"))

	def test_invalid_no_prefix(self):
		self.assertFalse(PAYMENT_ID_PATTERN.match("abc123"))

	def test_invalid_wrong_prefix(self):
		self.assertIsNone(PAYMENT_ID_PATTERN.match("re_abc123"))

	def test_invalid_empty(self):
		self.assertIsNone(PAYMENT_ID_PATTERN.match(""))

	def test_invalid_injection(self):
		self.assertIsNone(PAYMENT_ID_PATTERN.match("tr_abc; DROP TABLE"))

	def test_invalid_path_traversal(self):
		self.assertIsNone(PAYMENT_ID_PATTERN.match("tr_../../../etc"))


if __name__ == "__main__":
	unittest.main()
