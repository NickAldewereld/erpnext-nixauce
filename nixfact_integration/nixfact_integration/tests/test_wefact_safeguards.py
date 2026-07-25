# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de schaduwmodus-safeguards op Fase 1-gedrag."""

import unittest
from types import SimpleNamespace

from nixfact_integration.utils.ubl_generator import valideer_factuur_doc


class TestHookBypass(unittest.TestCase):

    def test_wefact_factuur_wordt_niet_gevalideerd(self):
        # Status 'Verstuurd' + onvolledige data zou normaal blokkeren;
        # met een wefact_identifier moet de hook meteen returnen zonder
        # frappe.get_doc aan te roepen (die er in de test niet is).
        doc = SimpleNamespace(
            status="Verstuurd",
            wefact_identifier="123",
            name="F-IMPORT-1",
        )
        # Mag niet raisen en niets teruggeven.
        self.assertIsNone(valideer_factuur_doc(doc))

    def test_niet_wefact_factuur_gaat_wel_de_validatie_in(self):
        # Zonder wefact_identifier en met status 'Concept' returnt de hook
        # ook (concept wordt niet gevalideerd) — bewijst dat de bypass niet
        # de enige exit is.
        doc = SimpleNamespace(status="Concept", wefact_identifier=None)
        self.assertIsNone(valideer_factuur_doc(doc))


class TestNummerbehoud(unittest.TestCase):

    def test_bestaand_nummer_blijft_behouden(self):
        # Een geïmporteerde factuur heeft factuurnummer al gezet (WeFact-code);
        # set_nummer_for_doc mag die niet overschrijven en moet doc.name = die
        # waarde zetten, zonder de DB-nummergenerator aan te roepen.
        from nixfact_integration.utils.numbering import set_nummer_for_doc

        doc = SimpleNamespace(factuurnummer="F0790", name=None)
        set_nummer_for_doc(doc, "NixFact Factuur")
        self.assertEqual(doc.factuurnummer, "F0790")
        self.assertEqual(doc.name, "F0790")


if __name__ == "__main__":
    unittest.main()
