# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor inkoopfactuur-mapping (puur, platte bedragen)."""

import unittest

from nixfact_integration.wefact_sync.mapping.inkoop import inkoop_to_dict


def _wf(**over):
    basis = {
        "Identifier": "337", "CreditInvoiceCode": "CF0337",
        "InvoiceCode": "01286", "CreditorCode": "CD0076",
        "Date": "2026-05-01", "AmountExcl": "200.00",
        "InvoiceLines": [
            {"Description": "Dienst", "PriceExcl": "150.00", "TaxPercentage": "21"},
            {"Description": "Dienst 2", "PriceExcl": "50.00", "TaxPercentage": "21"},
        ],
        "Attachments": [{"Identifier": 5, "Filename": "bon.pdf"}],
    }
    basis.update(over)
    return basis


class TestInkoop(unittest.TestCase):

    def test_kop(self):
        d = inkoop_to_dict(_wf())
        self.assertEqual(d["inkoopfactuur_nr"], "CF0337")
        self.assertEqual(d["betalingskenmerk"], "01286")
        self.assertEqual(d["wefact_creditor_code"], "CD0076")
        self.assertEqual(d["wefact_identifier"], "337")

    def test_bedrag_uit_amountexcl(self):
        d = inkoop_to_dict(_wf())
        self.assertEqual(d["bedrag_excl"], 200.0)
        self.assertEqual(d["btw_percentage"], 21.0)

    def test_attachments_doorgegeven(self):
        d = inkoop_to_dict(_wf())
        self.assertEqual(len(d["attachments"]), 1)
        self.assertEqual(d["attachments"][0]["Identifier"], 5)


if __name__ == "__main__":
    unittest.main()
