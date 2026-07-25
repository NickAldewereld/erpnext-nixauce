# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor het pure runrapport."""

import unittest

from nixfact_integration.wefact_sync.report import Mislukking, vat_rapport


class TestRapport(unittest.TestCase):

    def test_alles_goed(self):
        tekst = vat_rapport(815, [], "facturen")
        self.assertIn("815", tekst)
        self.assertIn("0 mislukt", tekst)

    def test_mislukkingen_worden_opgesomd(self):
        m = [
            Mislukking("factuur", "F0790", "klant onbekend"),
            Mislukking("factuur", "F0791", "datum ontbreekt"),
        ]
        tekst = vat_rapport(813, m, "facturen")
        self.assertIn("2 mislukt", tekst)
        self.assertIn("F0790", tekst)
        self.assertIn("klant onbekend", tekst)
        self.assertIn("F0791", tekst)

    def test_geen_waarschuwingen_ongewijzigd(self):
        tekst = vat_rapport(10, [], "facturen")
        self.assertNotIn("waarschuwing", tekst)

    def test_waarschuwingen_worden_opgesomd(self):
        w = ["factuur F0790: onbekende WeFact-status, geïmporteerd als Concept"]
        tekst = vat_rapport(10, [], "facturen", waarschuwingen=w)
        self.assertIn("1 waarschuwing", tekst)
        self.assertIn("F0790", tekst)
        self.assertIn("10 verwerkt", tekst)
        self.assertIn("0 mislukt", tekst)


if __name__ == "__main__":
    unittest.main()
