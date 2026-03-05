# Copyright (c) 2026, Nick Aldewereld
# License: MIT

"""Tests for UBL 2.1 XML generation."""

import unittest

from nixfact_integration.utils.ubl_generator import (
	NS_INVOICE,
	NS_CAC,
	NS_CBC,
	NSMAP,
)


class TestUBLNamespaces(unittest.TestCase):
	"""Verify UBL namespaces are correctly defined."""

	def test_invoice_namespace(self):
		self.assertIn("Invoice-2", NS_INVOICE)

	def test_cac_namespace(self):
		self.assertIn("CommonAggregateComponents-2", NS_CAC)

	def test_cbc_namespace(self):
		self.assertIn("CommonBasicComponents-2", NS_CBC)

	def test_nsmap_has_default(self):
		self.assertIn(None, NSMAP)
		self.assertEqual(NSMAP[None], NS_INVOICE)

	def test_nsmap_has_cac(self):
		self.assertIn("cac", NSMAP)

	def test_nsmap_has_cbc(self):
		self.assertIn("cbc", NSMAP)


class TestUBLHelpers(unittest.TestCase):
	"""Test XML builder helper functions."""

	def test_cac_tag(self):
		from nixfact_integration.utils.ubl_generator import _cac
		tag = _cac("Party")
		self.assertEqual(tag, f"{{{NS_CAC}}}Party")

	def test_cbc_tag(self):
		from nixfact_integration.utils.ubl_generator import _cbc
		tag = _cbc("ID")
		self.assertEqual(tag, f"{{{NS_CBC}}}ID")


if __name__ == "__main__":
	unittest.main()
