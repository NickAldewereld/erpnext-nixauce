# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de verkoop-creditnota-mapping (puur)."""

import unittest

from nixfact_integration.wefact_sync.mapping.creditnota import (
    creditnota_to_factuur,
)


def _wf_credit(**over):
    basis = {
        "Identifier": "900",
        "InvoiceCode": "C0007",
        "DebtorCode": "DB0042",
        "Date": "2026-04-01",
        "AmountIncl": "-121.00",
        "Translations": {"Status": "Creditfactuur"},
        "InvoiceLines": [
            {"Description": "Correctie advies", "Number": "1",
             "PriceExcl": "100.00", "TaxCode": "V21", "TaxPercentage": "21"},
        ],
    }
    basis.update(over)
    return basis


class TestCreditnota(unittest.TestCase):

    def test_gemarkeerd_als_creditnota(self):
        f = creditnota_to_factuur(_wf_credit())
        self.assertTrue(f["is_creditnota"])
        self.assertEqual(f["factuurnummer"], "C0007")

    def test_regelbedrag_wordt_negatief(self):
        f = creditnota_to_factuur(_wf_credit())
        self.assertEqual(f["regels"][0]["eenheidsprijs"], -100.0)

    def test_al_negatief_bedrag_blijft_negatief(self):
        wf = _wf_credit(InvoiceLines=[{
            "Description": "x", "Number": "1", "PriceExcl": "-50.00",
            "TaxCode": "V21", "TaxPercentage": "21"}])
        f = creditnota_to_factuur(wf)
        self.assertEqual(f["regels"][0]["eenheidsprijs"], -50.0)

    def test_html_gestript(self):
        wf = _wf_credit(InvoiceLines=[{
            "Description": "<b>Correctie</b>", "Number": "1",
            "PriceExcl": "10.00", "TaxCode": "V21", "TaxPercentage": "21"}])
        f = creditnota_to_factuur(wf)
        self.assertEqual(f["regels"][0]["omschrijving"], "Correctie")


if __name__ == "__main__":
    unittest.main()
