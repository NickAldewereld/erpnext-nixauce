# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

import unittest

from nixfact_integration.utils.tokens import generate_accept_token


class TestAcceptToken(unittest.TestCase):
    def test_default_length(self):
        t = generate_accept_token()
        # 24 bytes → 32 chars after base64-url
        self.assertGreaterEqual(len(t), 32)

    def test_uniqueness(self):
        tokens = {generate_accept_token() for _ in range(100)}
        self.assertEqual(len(tokens), 100)

    def test_url_safe(self):
        t = generate_accept_token()
        for forbidden in ("/", "+", "=", " ", "\n"):
            self.assertNotIn(forbidden, t)


if __name__ == "__main__":
    unittest.main()
