# tests/test_offerte_portal_api.py
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later

import unittest


class TestEmailValidation(unittest.TestCase):
    def test_valid(self):
        from nixfact_integration.api.offerte_portal import _is_valid_email
        for good in (
            "klant@example.com",
            "voor.naam+tag@sub.example.co.uk",
            "a@b.io",
        ):
            self.assertTrue(_is_valid_email(good), good)

    def test_invalid(self):
        from nixfact_integration.api.offerte_portal import _is_valid_email
        for bad in ("", None, "no-at", "@nodomain", "spaces in@x.com",
                    "x" * 320 + "@x.com", "a@b"):
            self.assertFalse(_is_valid_email(bad), repr(bad))


class TestSignatureValidation(unittest.TestCase):
    PNG_1X1 = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR4nGNgYGBgAAAABQABh6FO1AAAAABJRU5ErkJggg=="
    )

    def test_valid_png(self):
        from nixfact_integration.api.offerte_portal import _is_valid_signature
        self.assertTrue(_is_valid_signature(self.PNG_1X1))

    def test_rejects_non_png(self):
        from nixfact_integration.api.offerte_portal import _is_valid_signature
        for bad in (
            "data:image/jpeg;base64,xxx",
            "not a data url",
            "",
            None,
            "data:text/html;base64,xxx",
        ):
            self.assertFalse(_is_valid_signature(bad), repr(bad))

    def test_rejects_oversize(self):
        from nixfact_integration.api.offerte_portal import _is_valid_signature
        big = "data:image/png;base64," + ("A" * 2_000_000)
        self.assertFalse(_is_valid_signature(big))
