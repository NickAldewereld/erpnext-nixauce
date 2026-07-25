# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor status- en debiteurmapping (puur)."""

import unittest

from nixfact_integration.wefact_sync.mapping.status import nixfact_status
from nixfact_integration.wefact_sync.mapping.debtor import (
    debtor_to_address,
    debtor_to_customer,
)


class TestStatus(unittest.TestCase):

    def test_verzonden(self):
        r = nixfact_status("Verzonden", 100.0)
        self.assertEqual(r.status, "Verstuurd")
        self.assertFalse(r.is_creditnota)
        self.assertFalse(r.onbekend)

    def test_betaald(self):
        self.assertEqual(nixfact_status("Betaald", 100.0).status, "Betaald")

    def test_concept(self):
        self.assertEqual(nixfact_status("Concept", 100.0).status, "Concept")

    def test_negatief_bedrag_is_creditnota(self):
        r = nixfact_status("Betaald", -50.0)
        self.assertTrue(r.is_creditnota)

    def test_credit_in_tekst_is_creditnota(self):
        r = nixfact_status("Creditfactuur", -50.0)
        self.assertTrue(r.is_creditnota)

    def test_onbekende_status_valt_terug_op_concept_met_vlag(self):
        r = nixfact_status("Iets Nieuws", 100.0)
        self.assertEqual(r.status, "Concept")
        self.assertTrue(r.onbekend)


class TestDebtorCustomer(unittest.TestCase):

    def _bedrijf(self):
        return {
            "Identifier": "42",
            "DebtorCode": "DB0042",
            "CompanyName": "Klant B.V.",
            "Initials": "J",
            "SurName": "Jansen",
            "TaxNumber": "NL999999999B01",
            "Address": "Dorpsstraat 1",
            "ZipCode": "3511 AA",
            "City": "Utrecht",
            "Country": "NL",
        }

    def test_bedrijf_naam_en_type(self):
        c = debtor_to_customer(self._bedrijf())
        self.assertEqual(c["customer_name"], "Klant B.V.")
        self.assertEqual(c["customer_type"], "Company")
        self.assertEqual(c["tax_id"], "NL999999999B01")
        self.assertEqual(c["wefact_identifier"], "42")
        self.assertEqual(c["wefact_debtor_code"], "DB0042")

    def test_persoon_zonder_bedrijfsnaam(self):
        wf = self._bedrijf()
        wf["CompanyName"] = ""
        c = debtor_to_customer(wf)
        self.assertEqual(c["customer_name"], "J Jansen")
        self.assertEqual(c["customer_type"], "Individual")

    def test_adres(self):
        a = debtor_to_address(self._bedrijf())
        self.assertEqual(a["address_line1"], "Dorpsstraat 1")
        self.assertEqual(a["city"], "Utrecht")
        self.assertEqual(a["pincode"], "3511 AA")
        self.assertEqual(a["country_code"], "NL")

    def test_geen_adres_geeft_none(self):
        wf = self._bedrijf()
        wf["Address"] = ""
        wf["City"] = ""
        self.assertIsNone(debtor_to_address(wf))


if __name__ == "__main__":
    unittest.main()
