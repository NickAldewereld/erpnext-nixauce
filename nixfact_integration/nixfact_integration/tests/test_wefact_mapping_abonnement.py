# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor abonnement-mapping (puur)."""

import unittest

from nixfact_integration.wefact_sync.mapping.abonnement import (
    abonnement_to_dict,
    wefact_frequentie,
)


class TestFrequentie(unittest.TestCase):

    def test_maand(self):
        self.assertEqual(wefact_frequentie("m"), "Maandelijks")

    def test_kwartaal(self):
        self.assertEqual(wefact_frequentie("k"), "Kwartaal")

    def test_jaar(self):
        self.assertEqual(wefact_frequentie("j"), "Jaarlijks")

    def test_onbekend(self):
        self.assertEqual(wefact_frequentie("x"), "Maandelijks")


class TestAbonnement(unittest.TestCase):

    def test_velden(self):
        wf = {"Identifier": "12", "DebtorCode": "DB0160",
               "Description": "Hosting", "PriceExcl": "10.00",
               "TaxPercentage": "21", "Periodic": "m", "NextDate": "2026-08-01"}
        d = abonnement_to_dict(wf)
        self.assertEqual(d["klant_debtor_code"], "DB0160")
        self.assertEqual(d["bedrag_excl_btw"], 10.0)
        self.assertEqual(d["frequentie"], "Maandelijks")
        self.assertEqual(d["volgende_factuur_datum"], "2026-08-01")
        self.assertEqual(d["wefact_identifier"], "12")


if __name__ == "__main__":
    unittest.main()
