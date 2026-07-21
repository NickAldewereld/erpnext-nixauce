# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de omzetting van factuurregels naar rekendicts."""

import unittest
from types import SimpleNamespace

from nixfact_integration.nixfact_integration.doctype.nixfact_factuur import (
    nixfact_factuur,
)


def _regel(omschrijving, aantal, prijs, categorie, pct):
    return SimpleNamespace(
        omschrijving=omschrijving,
        aantal=aantal,
        eenheidsprijs=prijs,
        btw_categorie=categorie,
        btw_percentage=pct,
        regel_excl=None,
    )


class TestRegelsAlsDicts(unittest.TestCase):

    def test_vertaalt_categorie_naar_code(self):
        doc = SimpleNamespace(regels=[_regel("Advies", 1, 100, "Verlegd", 0)])
        result = nixfact_factuur.regels_als_dicts(doc)
        self.assertEqual(result[0]["btw_code"], "AE")

    def test_berekent_regeltotaal(self):
        doc = SimpleNamespace(regels=[_regel("Uren", 8, 125, "Standaard", 21)])
        result = nixfact_factuur.regels_als_dicts(doc)
        self.assertEqual(result[0]["excl"], 1000.00)

    def test_schrijft_regeltotaal_terug_op_de_regel(self):
        regel = _regel("Uren", 8, 125, "Standaard", 21)
        doc = SimpleNamespace(regels=[regel])
        nixfact_factuur.regels_als_dicts(doc)
        self.assertEqual(regel.regel_excl, 1000.00)

    def test_geen_regels(self):
        doc = SimpleNamespace(regels=[])
        self.assertEqual(nixfact_factuur.regels_als_dicts(doc), [])

    def test_regels_attribuut_ontbreekt(self):
        doc = SimpleNamespace()
        self.assertEqual(nixfact_factuur.regels_als_dicts(doc), [])


if __name__ == "__main__":
    unittest.main()
