# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de pure base64-decode van bijlagen."""

import base64
import unittest

from nixfact_integration.wefact_sync.attachments import decode_base64


class TestDecode(unittest.TestCase):

    def test_decode_ok(self):
        raw = b"%PDF-1.4 test"
        att = {"Base64": base64.b64encode(raw).decode(), "Filename": "bon.pdf"}
        data, naam = decode_base64(att)
        self.assertEqual(data, raw)
        self.assertEqual(naam, "bon.pdf")

    def test_lege_base64_faalt(self):
        with self.assertRaises(ValueError):
            decode_base64({"Base64": "", "Filename": "x.pdf"})

    def test_lowercase_key(self):
        raw = b"data"
        att = {"base64": base64.b64encode(raw).decode(), "Filename": "y.pdf"}
        self.assertEqual(decode_base64(att)[0], raw)


if __name__ == "__main__":
    unittest.main()
