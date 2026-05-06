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


class TestAcceptedImmutability(unittest.TestCase):
    def _make_doc(self, *, current_sig, old_sig):
        doc = MagicMock(spec=NixFactOfferte)
        doc.ondertekend_op = "2026-05-06 14:00:00"
        doc.handtekening = current_sig
        doc.ondertekend_door_email = "klant@example.com"
        doc.ondertekend_ip = "1.2.3.4"
        doc.ondertekend_user_agent = "ua"
        doc.is_new = MagicMock(return_value=False)
        old = MagicMock()
        old.handtekening = old_sig
        old.ondertekend_op = "2026-05-06 14:00:00"
        old.ondertekend_door_email = "klant@example.com"
        old.ondertekend_ip = "1.2.3.4"
        old.ondertekend_user_agent = "ua"
        doc.get_doc_before_save = MagicMock(return_value=old)
        return doc

    def test_signature_change_after_accept_blocked(self):
        doc = self._make_doc(current_sig="tampered", old_sig="original")
        with self.assertRaises(Exception):
            NixFactOfferte._guard_immutable_after_accept(doc)

    def test_unchanged_audit_passes(self):
        doc = self._make_doc(current_sig="original", old_sig="original")
        NixFactOfferte._guard_immutable_after_accept(doc)  # no raise

    def test_unsigned_offerte_is_editable(self):
        doc = MagicMock(spec=NixFactOfferte)
        doc.ondertekend_op = None
        doc.is_new = MagicMock(return_value=False)
        # Should return immediately, no exception
        NixFactOfferte._guard_immutable_after_accept(doc)


if __name__ == "__main__":
    unittest.main()
