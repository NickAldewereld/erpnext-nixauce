# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor crediteur-mapping (puur)."""

import unittest

from nixfact_integration.wefact_sync.mapping.creditor import (
    creditor_to_supplier,
)


class TestCreditor(unittest.TestCase):

    def _wf(self, **over):
        basis = {"Identifier": "77", "CreditorCode": "CD0076",
                 "CompanyName": "Leverancier B.V.", "TaxNumber": "NL1B01"}
        basis.update(over)
        return basis

    def test_naam_en_codes(self):
        s = creditor_to_supplier(self._wf())
        self.assertEqual(s["supplier_name"], "Leverancier B.V.")
        self.assertEqual(s["wefact_identifier"], "77")
        self.assertEqual(s["wefact_creditor_code"], "CD0076")
        self.assertEqual(s["tax_id"], "NL1B01")

    def test_lege_naam_valt_terug_op_code(self):
        s = creditor_to_supplier(self._wf(CompanyName=""))
        self.assertEqual(s["supplier_name"], "WeFact CD0076")


if __name__ == "__main__":
    unittest.main()
