# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de Peppol-validatie met Nederlandse meldingen."""

import unittest

from nixfact_integration.utils.ubl_model import UBLFactuur, UBLPartij, UBLRegel
from nixfact_integration.utils.ubl_validatie import valideer


def _geldige_factuur():
    partij = UBLPartij(
        naam="Aldewereld Consultancy",
        btw_nummer="NL002168402B79",
        straat="Prunuslaan 53",
        plaats="Amstelveen",
        postcode="1185 KT",
        landcode="NL",
    )
    afnemer = UBLPartij(
        naam="Klant B.V.",
        btw_nummer="NL999999999B01",
        straat="Dorpsstraat 1",
        plaats="Utrecht",
        postcode="3511 AA",
        landcode="NL",
    )
    return UBLFactuur(
        nummer="2026-0042",
        factuurdatum="2026-07-21",
        vervaldatum="2026-08-04",
        leverancier=partij,
        afnemer=afnemer,
        regels=[UBLRegel("Advies", 8, 125.00, 1000.00, 21, "S")],
        iban="NL02ABNA0123456789",
    )


def _codes(fouten):
    return {f.regel for f in fouten}


class TestGeldigeFactuur(unittest.TestCase):

    def test_geen_fouten(self):
        self.assertEqual(valideer(_geldige_factuur()), [])


class TestVerplichteVelden(unittest.TestCase):

    def test_nummer_ontbreekt(self):
        f = _geldige_factuur()
        f.nummer = ""
        self.assertIn("BR-02", _codes(valideer(f)))

    def test_datum_ontbreekt(self):
        f = _geldige_factuur()
        f.factuurdatum = ""
        self.assertIn("BR-03", _codes(valideer(f)))

    def test_geen_regels(self):
        f = _geldige_factuur()
        f.regels = []
        self.assertIn("BR-16", _codes(valideer(f)))

    def test_leveranciersnaam_ontbreekt(self):
        f = _geldige_factuur()
        f.leverancier.naam = ""
        self.assertIn("BR-06", _codes(valideer(f)))

    def test_afnemernaam_ontbreekt(self):
        f = _geldige_factuur()
        f.afnemer.naam = ""
        self.assertIn("BR-07", _codes(valideer(f)))

    def test_leveranciersadres_ontbreekt(self):
        f = _geldige_factuur()
        f.leverancier.plaats = ""
        self.assertIn("BR-08", _codes(valideer(f)))

    def test_afnemerland_ontbreekt(self):
        f = _geldige_factuur()
        f.afnemer.landcode = ""
        self.assertIn("BR-09", _codes(valideer(f)))


class TestBtwRegels(unittest.TestCase):

    def test_verlegd_met_percentage_is_fout(self):
        f = _geldige_factuur()
        f.regels = [UBLRegel("Advies", 1, 100.00, 100.00, 21, "AE")]
        self.assertIn("BR-AE-01", _codes(valideer(f)))

    def test_standaard_zonder_percentage_is_fout(self):
        f = _geldige_factuur()
        f.regels = [UBLRegel("Advies", 1, 100.00, 100.00, 0, "S")]
        self.assertIn("BR-S-01", _codes(valideer(f)))

    def test_onbekende_categorie_is_fout(self):
        f = _geldige_factuur()
        f.regels = [UBLRegel("Advies", 1, 100.00, 100.00, 21, "X")]
        self.assertIn("BR-CL-01", _codes(valideer(f)))

    def test_verlegd_zonder_btw_nummer_afnemer_is_fout(self):
        f = _geldige_factuur()
        f.afnemer.btw_nummer = ""
        f.regels = [UBLRegel("Advies", 1, 100.00, 100.00, 0, "AE")]
        self.assertIn("BR-AE-09", _codes(valideer(f)))

    def test_onbekende_categorie_en_fout_totaal_geeft_beide_fouten(self):
        f = _geldige_factuur()
        f.regels = [UBLRegel("Advies", 2, 100.00, 999.00, 21, "X")]
        codes = _codes(valideer(f))
        self.assertIn("BR-CL-01", codes)
        self.assertIn("BR-CO-04", codes)


class TestRegelInhoud(unittest.TestCase):

    def test_regel_zonder_omschrijving(self):
        f = _geldige_factuur()
        f.regels = [UBLRegel("", 1, 100.00, 100.00, 21, "S")]
        self.assertIn("BR-25", _codes(valideer(f)))

    def test_regeltotaal_klopt_niet_met_aantal_maal_prijs(self):
        f = _geldige_factuur()
        f.regels = [UBLRegel("Advies", 2, 100.00, 999.00, 21, "S")]
        self.assertIn("BR-CO-04", _codes(valideer(f)))


class TestMeldingen(unittest.TestCase):

    def test_melding_is_nederlands_en_noemt_het_veld(self):
        f = _geldige_factuur()
        f.nummer = ""
        melding = valideer(f)[0].melding
        self.assertIn("factuurnummer", melding.lower())

    def test_regelfout_noemt_het_regelnummer(self):
        f = _geldige_factuur()
        f.regels = [
            UBLRegel("Advies", 1, 100.00, 100.00, 21, "S"),
            UBLRegel("", 1, 100.00, 100.00, 21, "S"),
        ]
        fouten = [f_ for f_ in valideer(f) if f_.regel == "BR-25"]
        self.assertIn("regel 2", fouten[0].melding.lower())


if __name__ == "__main__":
    unittest.main()
