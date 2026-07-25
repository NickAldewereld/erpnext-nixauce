# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor verkoopfactuurmapping (puur), met echte WeFact-veldnamen."""

import unittest

from nixfact_integration.wefact_sync.mapping.invoice import (
    btw_categorie,
    invoice_to_factuur,
)


def _wf_factuur(**over):
    basis = {
        "Identifier": "815",
        "InvoiceCode": "F0790",
        "DebtorCode": "DB0042",
        "Date": "2026-03-01",
        "ReferenceNumber": "PO-9001",
        "AmountIncl": "242.00",
        "Translations": {"Status": "Verzonden"},
        "InvoiceLines": [
            {
                "Description": "Advies",
                "Number": "8",
                "PriceExcl": "125.00",
                "TaxCode": "V21",
                "TaxPercentage": "21",
            },
            {
                "Description": "Hosting",
                "Number": "1",
                "PriceExcl": "100.00",
                "TaxCode": "V0",
                "TaxPercentage": "0",
            },
        ],
    }
    basis.update(over)
    return basis


class TestBtwCategorie(unittest.TestCase):

    def test_standaard(self):
        self.assertEqual(btw_categorie("V21", 21), "Standaard")

    def test_nultarief(self):
        self.assertEqual(btw_categorie("V0", 0), "Nultarief")


class TestInvoiceToFactuur(unittest.TestCase):

    def test_kopvelden(self):
        f = invoice_to_factuur(_wf_factuur())
        self.assertEqual(f["factuurnummer"], "F0790")
        self.assertEqual(f["factuur_datum"], "2026-03-01")
        self.assertEqual(f["referentie"], "PO-9001")
        self.assertEqual(f["wefact_identifier"], "815")
        self.assertEqual(f["wefact_debtor_code"], "DB0042")
        self.assertEqual(f["status"], "Verstuurd")
        self.assertFalse(f["is_creditnota"])

    def test_regels(self):
        f = invoice_to_factuur(_wf_factuur())
        self.assertEqual(len(f["regels"]), 2)
        r0 = f["regels"][0]
        self.assertEqual(r0["omschrijving"], "Advies")
        self.assertEqual(r0["aantal"], 8.0)
        self.assertEqual(r0["eenheidsprijs"], 125.0)
        self.assertEqual(r0["btw_categorie"], "Standaard")
        self.assertEqual(r0["btw_percentage"], 21.0)
        self.assertEqual(f["regels"][1]["btw_categorie"], "Nultarief")

    def test_creditnota_negatief(self):
        wf = _wf_factuur(AmountIncl="-242.00",
                         Translations={"Status": "Creditfactuur"})
        f = invoice_to_factuur(wf)
        self.assertTrue(f["is_creditnota"])

    def test_onbekende_status_gemarkeerd(self):
        wf = _wf_factuur(Translations={"Status": "Supernieuw"})
        f = invoice_to_factuur(wf)
        self.assertEqual(f["status"], "Concept")
        self.assertTrue(f["onbekende_status"])

    def test_lege_invoicelines(self):
        wf = _wf_factuur(InvoiceLines=[])
        f = invoice_to_factuur(wf)
        self.assertEqual(f["regels"], [])


class TestStripHtml(unittest.TestCase):

    def test_html_wordt_gestript(self):
        from nixfact_integration.wefact_sync.mapping.invoice import strip_html
        self.assertEqual(strip_html("<b>Advies</b> over <strong>Google</strong>"),
                         "Advies over Google")

    def test_witruimte_genormaliseerd(self):
        from nixfact_integration.wefact_sync.mapping.invoice import strip_html
        self.assertEqual(strip_html("regel1\n\n   regel2"), "regel1 regel2")

    def test_lange_html_omschrijving_in_regel(self):
        wf = _wf_factuur(InvoiceLines=[{
            "Description": "<strong>Wij verzorgen</strong> als bureau een uitgebreide analyse",
            "Number": "1", "PriceExcl": "500.00", "TaxCode": "V21", "TaxPercentage": "21",
        }])
        r = invoice_to_factuur(wf)["regels"][0]
        self.assertNotIn("<", r["omschrijving"])
        self.assertIn("Wij verzorgen als bureau", r["omschrijving"])


if __name__ == "__main__":
    unittest.main()
