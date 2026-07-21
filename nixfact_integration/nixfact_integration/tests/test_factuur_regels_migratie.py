# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de migratie van bedragfacturen naar regelfacturen."""

import unittest

from nixfact_integration.patches.v1_0.factuur_regels_migratie import (
    bepaal_migratie_regel,
)


class TestBepaalMigratieRegel(unittest.TestCase):

    def test_bedrag_wordt_eenheidsprijs(self):
        regel = bepaal_migratie_regel(
            {"bedrag_excl_btw": 250.00, "btw_percentage": 21}
        )
        self.assertEqual(regel["eenheidsprijs"], 250.00)
        self.assertEqual(regel["aantal"], 1)

    def test_percentage_wordt_overgenomen(self):
        regel = bepaal_migratie_regel(
            {"bedrag_excl_btw": 100.00, "btw_percentage": 9}
        )
        self.assertEqual(regel["btw_percentage"], 9)
        self.assertEqual(regel["btw_categorie"], "Standaard")

    def test_nul_procent_wordt_nultarief(self):
        regel = bepaal_migratie_regel(
            {"bedrag_excl_btw": 100.00, "btw_percentage": 0}
        )
        self.assertEqual(regel["btw_categorie"], "Nultarief")

    def test_omschrijving_uit_referentie(self):
        regel = bepaal_migratie_regel(
            {"bedrag_excl_btw": 100.00, "btw_percentage": 21,
             "referentie": "Project Alpha"}
        )
        self.assertEqual(regel["omschrijving"], "Project Alpha")

    def test_omschrijving_valt_terug_op_factuurnummer(self):
        regel = bepaal_migratie_regel(
            {"bedrag_excl_btw": 100.00, "btw_percentage": 21,
             "factuurnummer": "2026-0001"}
        )
        self.assertEqual(regel["omschrijving"], "Factuur 2026-0001")

    def test_omschrijving_laatste_redmiddel(self):
        regel = bepaal_migratie_regel({"bedrag_excl_btw": 100.00})
        self.assertEqual(regel["omschrijving"], "Gemigreerde factuurregel")


if __name__ == "__main__":
    unittest.main()
