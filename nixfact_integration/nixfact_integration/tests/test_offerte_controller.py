# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Pure-logic tests for the NixFact Offerte controller."""

import unittest
from unittest.mock import MagicMock

from nixfact_integration.doctype.nixfact_offerte.nixfact_offerte import (
    NixFactOfferte,
)


class TestBeforeInsertToken(unittest.TestCase):
    def test_generates_token_when_missing(self):
        doc = MagicMock(spec=NixFactOfferte)
        doc.accept_token = None
        NixFactOfferte.before_insert(doc)
        self.assertIsNotNone(doc.accept_token)
        self.assertGreaterEqual(len(doc.accept_token), 32)

    def test_preserves_existing_token(self):
        doc = MagicMock(spec=NixFactOfferte)
        doc.accept_token = "preset-token"
        NixFactOfferte.before_insert(doc)
        self.assertEqual(doc.accept_token, "preset-token")


if __name__ == "__main__":
    unittest.main()
