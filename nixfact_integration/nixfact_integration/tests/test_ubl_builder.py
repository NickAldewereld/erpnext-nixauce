# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de pure UBL 2.1 / Peppol BIS 3.0 builder."""

import unittest

from lxml import etree

from nixfact_integration.utils.ubl_builder import (
    NS_CAC,
    NS_CBC,
    build_invoice_xml,
)
from nixfact_integration.utils.ubl_model import UBLFactuur, UBLPartij, UBLRegel

NS = {"cac": NS_CAC, "cbc": NS_CBC}


def _partij(naam="Aldewereld Consultancy", btw="NL002168402B79"):
    return UBLPartij(
        naam=naam,
        btw_nummer=btw,
        straat="Prunuslaan 53",
        plaats="Amstelveen",
        postcode="1185 KT",
        landcode="NL",
        email="ikben@nickaldewereld.nl",
    )


def _factuur(regels):
    return UBLFactuur(
        nummer="2026-0042",
        factuurdatum="2026-07-21",
        vervaldatum="2026-08-04",
        referentie="PO-9001",
        leverancier=_partij(),
        afnemer=_partij("Klant B.V.", "NL999999999B01"),
        regels=regels,
        iban="NL02ABNA0123456789",
        bic="ABNANL2A",
    )


def _xml(factuur):
    return etree.fromstring(build_invoice_xml(factuur).encode("utf-8"))


class TestMeerdereRegels(unittest.TestCase):

    def setUp(self):
        self.doc = _xml(
            _factuur(
                [
                    UBLRegel("Advies", 8, 125.00, 1000.00, 21, "S"),
                    UBLRegel("Licentie", 1, 200.00, 200.00, 9, "S"),
                ]
            )
        )

    def test_twee_invoice_lines(self):
        lijnen = self.doc.findall("cac:InvoiceLine", NS)
        self.assertEqual(len(lijnen), 2)

    def test_lijn_ids_zijn_oplopend(self):
        ids = [el.text for el in self.doc.findall("cac:InvoiceLine/cbc:ID", NS)]
        self.assertEqual(ids, ["1", "2"])

    def test_lijn_bedragen(self):
        bedragen = [
            el.text
            for el in self.doc.findall(
                "cac:InvoiceLine/cbc:LineExtensionAmount", NS
            )
        ]
        self.assertEqual(bedragen, ["1000.00", "200.00"])

    def test_lijn_omschrijving(self):
        namen = [
            el.text
            for el in self.doc.findall("cac:InvoiceLine/cac:Item/cbc:Name", NS)
        ]
        self.assertEqual(namen, ["Advies", "Licentie"])

    def test_aantal_per_regel(self):
        aantallen = [
            el.text
            for el in self.doc.findall(
                "cac:InvoiceLine/cbc:InvoicedQuantity", NS
            )
        ]
        self.assertEqual(aantallen, ["8", "1"])

    def test_eenheidsprijs_per_regel(self):
        prijzen = [
            el.text
            for el in self.doc.findall(
                "cac:InvoiceLine/cac:Price/cbc:PriceAmount", NS
            )
        ]
        self.assertEqual(prijzen, ["125.00", "200.00"])

    def test_twee_tax_subtotals(self):
        subs = self.doc.findall("cac:TaxTotal/cac:TaxSubtotal", NS)
        self.assertEqual(len(subs), 2)

    def test_tax_amount_is_som_van_groepen(self):
        bedrag = self.doc.find("cac:TaxTotal/cbc:TaxAmount", NS).text
        # 21% over 1000 = 210.00, 9% over 200 = 18.00
        self.assertEqual(bedrag, "228.00")

    def test_monetary_total(self):
        pad = "cac:LegalMonetaryTotal/cbc:{}"
        self.assertEqual(
            self.doc.find(pad.format("LineExtensionAmount"), NS).text, "1200.00"
        )
        self.assertEqual(
            self.doc.find(pad.format("TaxInclusiveAmount"), NS).text, "1428.00"
        )
        self.assertEqual(
            self.doc.find(pad.format("PayableAmount"), NS).text, "1428.00"
        )


class TestBtwCategorieen(unittest.TestCase):

    def test_verlegd_krijgt_code_ae(self):
        doc = _xml(_factuur([UBLRegel("Advies", 1, 500.00, 500.00, 0, "AE")]))
        code = doc.find(
            "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:ID", NS
        ).text
        self.assertEqual(code, "AE")

    def test_verlegd_krijgt_vrijstellingsreden(self):
        doc = _xml(_factuur([UBLRegel("Advies", 1, 500.00, 500.00, 0, "AE")]))
        reden = doc.find(
            "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory"
            "/cbc:TaxExemptionReason",
            NS,
        )
        self.assertIsNotNone(reden)
        self.assertEqual(reden.text, "Btw verlegd")

    def test_standaard_krijgt_geen_vrijstellingsreden(self):
        doc = _xml(_factuur([UBLRegel("Advies", 1, 500.00, 500.00, 21, "S")]))
        reden = doc.find(
            "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory"
            "/cbc:TaxExemptionReason",
            NS,
        )
        self.assertIsNone(reden)

    def test_regel_krijgt_eigen_classified_tax_category(self):
        doc = _xml(
            _factuur(
                [
                    UBLRegel("A", 1, 100.00, 100.00, 21, "S"),
                    UBLRegel("B", 1, 100.00, 100.00, 0, "AE"),
                ]
            )
        )
        codes = [
            el.text
            for el in doc.findall(
                "cac:InvoiceLine/cac:Item/cac:ClassifiedTaxCategory/cbc:ID", NS
            )
        ]
        self.assertEqual(codes, ["S", "AE"])


class TestKopvelden(unittest.TestCase):

    def setUp(self):
        self.doc = _xml(_factuur([UBLRegel("A", 1, 100.00, 100.00, 21, "S")]))

    def test_customization_id(self):
        el = self.doc.find("cbc:CustomizationID", NS)
        self.assertIn("urn:cen.eu:en16931:2017", el.text)

    def test_factuurnummer(self):
        self.assertEqual(self.doc.find("cbc:ID", NS).text, "2026-0042")

    def test_type_code_380(self):
        self.assertEqual(self.doc.find("cbc:InvoiceTypeCode", NS).text, "380")

    def test_valuta_eur(self):
        self.assertEqual(
            self.doc.find("cbc:DocumentCurrencyCode", NS).text, "EUR"
        )

    def test_iban_in_payment_means(self):
        el = self.doc.find(
            "cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID", NS
        )
        self.assertEqual(el.text, "NL02ABNA0123456789")


class TestRobuustheid(unittest.TestCase):

    def test_controlekarakters_worden_gestript(self):
        doc = _xml(
            _factuur([UBLRegel("Ad\x00vies", 1, 100.00, 100.00, 21, "S")])
        )
        naam = doc.find("cac:InvoiceLine/cac:Item/cbc:Name", NS).text
        self.assertEqual(naam, "Advies")

    def test_deelbetaling_geeft_prepaid_amount(self):
        factuur = _factuur([UBLRegel("A", 1, 100.00, 100.00, 21, "S")])
        factuur.betaald_bedrag = 21.00
        doc = _xml(factuur)
        self.assertEqual(
            doc.find("cac:LegalMonetaryTotal/cbc:PrepaidAmount", NS).text,
            "21.00",
        )
        self.assertEqual(
            doc.find("cac:LegalMonetaryTotal/cbc:PayableAmount", NS).text,
            "100.00",
        )

    def test_geen_deelbetaling_geeft_geen_prepaid_amount(self):
        factuur = _factuur([UBLRegel("A", 1, 100.00, 100.00, 21, "S")])
        doc = _xml(factuur)
        self.assertIsNone(
            doc.find("cac:LegalMonetaryTotal/cbc:PrepaidAmount", NS)
        )

    def test_id_en_issue_date_altijd_aanwezig(self):
        doc = _xml(_factuur([UBLRegel("A", 1, 100.00, 100.00, 21, "S")]))
        id_el = doc.find("cbc:ID", NS)
        issue_date_el = doc.find("cbc:IssueDate", NS)
        self.assertIsNotNone(id_el)
        self.assertIsNotNone(issue_date_el)
        self.assertTrue(id_el.text)
        self.assertTrue(issue_date_el.text)


if __name__ == "__main__":
    unittest.main()
