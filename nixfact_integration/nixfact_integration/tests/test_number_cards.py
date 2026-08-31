# tests/test_number_cards.py
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later

"""Pure tests for the Custom number-card methods in api/statistieken.py.

`frappe.db` is mocked — these tests only verify the shape of the returned
card payload, the role gate, and the filters/query the methods use.
"""

import unittest
from unittest.mock import MagicMock


def _statistieken():
    from nixfact_integration.api import statistieken

    return statistieken


class TestOmzetDezeMaandCard(unittest.TestCase):
    def test_returns_currency_value(self):
        st = _statistieken()
        st.frappe.get_roles = lambda: ["System Manager"]
        st.frappe.db = MagicMock()
        st.frappe.db.sql.return_value = [(1234.5,)]

        result = st.get_omzet_deze_maand_card()

        self.assertEqual(result, {"value": 1234.5, "fieldtype": "Currency"})
        sql = st.frappe.db.sql.call_args[0][0]
        self.assertIn("status != 'Concept'", sql)

    def test_requires_accountant_role(self):
        st = _statistieken()
        st.frappe.get_roles = lambda: ["Employee"]

        with self.assertRaises(st.frappe.PermissionError):
            st.get_omzet_deze_maand_card()


class TestFacturenTeLaatCard(unittest.TestCase):
    def test_counts_overdue_open_invoices(self):
        st = _statistieken()
        st.frappe.get_roles = lambda: ["Accounts Manager"]
        st.frappe.db = MagicMock()
        st.frappe.db.count.return_value = 3

        result = st.get_facturen_te_laat_card()

        self.assertEqual(result, {"value": 3, "fieldtype": "Int"})
        args = st.frappe.db.count.call_args[0]
        self.assertEqual(args[0], "NixFact Factuur")
        filters = args[1]
        self.assertEqual(filters["vervaldatum"][0], "<")
        self.assertEqual(filters["status"][0], "in")
        self.assertIn("Verstuurd", filters["status"][1])
