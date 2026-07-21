# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor BTW-categorieën en regelberekening."""

import unittest

from nixfact_integration.utils.btw import (
    NUL_CATEGORIEEN,
    BtwGroep,
    code_voor_categorie,
    groepeer_btw,
    regel_excl,
    totalen,
)


class TestCategorieCodes(unittest.TestCase):

    def test_standaard(self):
        self.assertEqual(code_voor_categorie("Standaard"), "S")

    def test_verlegd(self):
        self.assertEqual(code_voor_categorie("Verlegd"), "AE")

    def test_nultarief(self):
        self.assertEqual(code_voor_categorie("Nultarief"), "Z")

    def test_vrijgesteld(self):
        self.assertEqual(code_voor_categorie("Vrijgesteld"), "E")

    def test_onbekend_valt_terug_op_standaard(self):
        self.assertEqual(code_voor_categorie("Zomaar iets"), "S")

    def test_leeg_valt_terug_op_standaard(self):
        self.assertEqual(code_voor_categorie(""), "S")

    def test_nul_categorieen(self):
        self.assertEqual(NUL_CATEGORIEEN, frozenset({"AE", "Z", "E"}))


class TestRegelExcl(unittest.TestCase):

    def test_simpel(self):
        self.assertEqual(regel_excl(2, 50), 100.00)

    def test_afronding_halve_cent_omhoog(self):
        # 3 x 10.005 = 30.015 -> 30.02
        self.assertEqual(regel_excl(3, 10.005), 30.02)

    def test_nul_aantal(self):
        self.assertEqual(regel_excl(0, 99), 0.00)

    def test_negatief_bedrag_toegestaan(self):
        # Kortingsregel.
        self.assertEqual(regel_excl(1, -25), -25.00)


class TestGroepeerBtw(unittest.TestCase):

    def test_een_groep(self):
        regels = [
            {"excl": 100.00, "btw_percentage": 21, "btw_code": "S"},
            {"excl": 50.00, "btw_percentage": 21, "btw_code": "S"},
        ]
        groepen = groepeer_btw(regels)
        self.assertEqual(groepen, [BtwGroep("S", 21.0, 150.00, 31.50)])

    def test_twee_percentages_apart(self):
        regels = [
            {"excl": 100.00, "btw_percentage": 21, "btw_code": "S"},
            {"excl": 100.00, "btw_percentage": 9, "btw_code": "S"},
        ]
        groepen = groepeer_btw(regels)
        self.assertEqual(len(groepen), 2)
        self.assertEqual(groepen[0], BtwGroep("S", 9.0, 100.00, 9.00))
        self.assertEqual(groepen[1], BtwGroep("S", 21.0, 100.00, 21.00))

    def test_verlegd_krijgt_nul_btw(self):
        regels = [{"excl": 200.00, "btw_percentage": 0, "btw_code": "AE"}]
        self.assertEqual(groepeer_btw(regels), [BtwGroep("AE", 0.0, 200.00, 0.00)])

    def test_btw_berekend_over_groepstotaal_niet_per_regel(self):
        # Twee regels van 0.10 bij 21%: per regel 0.021 -> 0.02 elk = 0.04,
        # over het groepstotaal 0.20 -> 0.042 -> 0.04. Hier gelijk, maar bij
        # 0.05 + 0.05 loopt het uiteen: per regel 0.01+0.01=0.02, groep 0.02.
        regels = [
            {"excl": 0.05, "btw_percentage": 21, "btw_code": "S"},
            {"excl": 0.05, "btw_percentage": 21, "btw_code": "S"},
        ]
        groepen = groepeer_btw(regels)
        self.assertEqual(groepen[0].btw, 0.02)

    def test_lege_regels(self):
        self.assertEqual(groepeer_btw([]), [])


class TestTotalen(unittest.TestCase):

    def test_gemengde_factuur(self):
        regels = [
            {"excl": 100.00, "btw_percentage": 21, "btw_code": "S"},
            {"excl": 100.00, "btw_percentage": 9, "btw_code": "S"},
            {"excl": 50.00, "btw_percentage": 0, "btw_code": "AE"},
        ]
        self.assertEqual(
            totalen(regels), {"excl": 250.00, "btw": 30.00, "incl": 280.00}
        )

    def test_leeg(self):
        self.assertEqual(totalen([]), {"excl": 0.00, "btw": 0.00, "incl": 0.00})


if __name__ == "__main__":
    unittest.main()
