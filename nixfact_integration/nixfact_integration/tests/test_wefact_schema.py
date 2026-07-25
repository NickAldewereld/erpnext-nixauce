# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de WeFact-schemavelden (pure spec-helper)."""

import unittest

from nixfact_integration.patches.v1_0.wefact_velden import custom_field_specs


class TestCustomFieldSpecs(unittest.TestCase):

    def test_customer_krijgt_beide_velden(self):
        specs = custom_field_specs()
        namen = [f["fieldname"] for f in specs["Customer"]]
        self.assertIn("wefact_identifier", namen)
        self.assertIn("wefact_debtor_code", namen)

    def test_identifier_is_data_en_indexeerbaar(self):
        specs = custom_field_specs()
        veld = next(
            f for f in specs["Customer"] if f["fieldname"] == "wefact_identifier"
        )
        self.assertEqual(veld["fieldtype"], "Data")
        self.assertEqual(veld.get("search_index"), 1)


if __name__ == "__main__":
    unittest.main()
