# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Pure-logic tests for the NixFact Offerte controller."""

import unittest
from unittest.mock import MagicMock

from nixfact_integration.nixfact_integration.doctype.nixfact_offerte.nixfact_offerte import (
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

    def _make_doc_tampered(self, *, field_to_change, new_value):
        """Build a doc + old_doc pair where exactly `field_to_change` differs."""
        baseline = {
            "handtekening": "data:image/png;base64,ORIGINAL",
            "ondertekend_op": "2026-05-06 14:00:00",
            "ondertekend_door_email": "klant@example.com",
            "ondertekend_ip": "1.2.3.4",
            "ondertekend_user_agent": "Mozilla/5.0",
        }
        doc = MagicMock(spec=NixFactOfferte)
        doc.is_new = MagicMock(return_value=False)
        for field, value in baseline.items():
            setattr(doc, field, value)
        # Apply the tamper on the doc side.
        setattr(doc, field_to_change, new_value)

        old = MagicMock()
        for field, value in baseline.items():
            setattr(old, field, value)
        # Old must always carry ondertekend_op for the guard to engage.
        doc.get_doc_before_save = MagicMock(return_value=old)
        return doc

    def test_signature_change_after_accept_blocked(self):
        doc = self._make_doc(current_sig="tampered", old_sig="original")
        with self.assertRaises(Exception):
            NixFactOfferte._guard_immutable_after_accept(doc)

    def test_unchanged_audit_passes(self):
        doc = self._make_doc(current_sig="original", old_sig="original")
        try:
            NixFactOfferte._guard_immutable_after_accept(doc)
        except Exception as e:  # noqa: BLE001
            self.fail(f"Guard raised unexpectedly on unchanged audit: {e}")

    def test_each_locked_field_blocks_tampering(self):
        cases = [
            ("handtekening", "data:image/png;base64,TAMPERED"),
            ("ondertekend_op", "2099-01-01 00:00:00"),
            ("ondertekend_door_email", "attacker@example.com"),
            ("ondertekend_ip", "9.9.9.9"),
            ("ondertekend_user_agent", "TamperedAgent/1.0"),
        ]
        for field, new_value in cases:
            with self.subTest(field=field):
                doc = self._make_doc_tampered(field_to_change=field, new_value=new_value)
                with self.assertRaises(Exception):
                    NixFactOfferte._guard_immutable_after_accept(doc)

    def test_unsigned_offerte_is_editable(self):
        doc = MagicMock(spec=NixFactOfferte)
        doc.ondertekend_op = None
        doc.is_new = MagicMock(return_value=False)
        old = MagicMock()
        old.ondertekend_op = None  # DB record also unsigned — guard must not engage.
        doc.get_doc_before_save = MagicMock(return_value=old)
        # Should return immediately, no exception
        NixFactOfferte._guard_immutable_after_accept(doc)

    def test_first_sign_not_blocked_by_guard(self):
        """The guard must allow the very first sign-save to pass.

        Pre-fix bug: the guard gated on self.ondertekend_op (always set
        on accept), not old.ondertekend_op (None until persisted), so it
        threw on every first sign. This test pins the fixed behaviour.
        """
        from datetime import datetime
        doc = MagicMock(spec=NixFactOfferte)
        doc.ondertekend_op = datetime(2026, 5, 7, 14, 0, 0)
        doc.handtekening = "data:image/png;base64,NEWSIG"
        doc.ondertekend_door_email = "klant@example.com"
        doc.ondertekend_ip = "1.2.3.4"
        doc.ondertekend_user_agent = "Mozilla/5.0"
        doc.is_new = MagicMock(return_value=False)
        old = MagicMock()
        # Critical: old record was UNSIGNED — this is the first-sign save.
        old.ondertekend_op = None
        old.handtekening = None
        old.ondertekend_door_email = None
        old.ondertekend_ip = None
        old.ondertekend_user_agent = None
        doc.get_doc_before_save = MagicMock(return_value=old)
        try:
            NixFactOfferte._guard_immutable_after_accept(doc)
        except Exception as e:  # noqa: BLE001
            self.fail(f"Guard incorrectly blocked first sign: {e}")


class TestPortalSentTimestamp(unittest.TestCase):
    def test_concept_to_verstuurd_stamps(self):
        doc = MagicMock(spec=NixFactOfferte)
        doc.status = "Verstuurd"
        doc.portal_verstuurd_op = None
        doc.is_new = MagicMock(return_value=False)
        old = MagicMock()
        old.status = "Concept"
        doc.get_doc_before_save = MagicMock(return_value=old)
        NixFactOfferte._stamp_portal_sent(doc)
        self.assertIsNotNone(doc.portal_verstuurd_op)

    def test_other_transitions_no_stamp(self):
        doc = MagicMock(spec=NixFactOfferte)
        doc.status = "Geaccepteerd"
        doc.portal_verstuurd_op = None
        doc.is_new = MagicMock(return_value=False)
        old = MagicMock()
        old.status = "Verstuurd"
        doc.get_doc_before_save = MagicMock(return_value=old)
        NixFactOfferte._stamp_portal_sent(doc)
        self.assertIsNone(doc.portal_verstuurd_op)

    def test_existing_stamp_not_overwritten(self):
        doc = MagicMock(spec=NixFactOfferte)
        doc.status = "Verstuurd"
        doc.portal_verstuurd_op = "2026-01-01 09:00:00"
        doc.is_new = MagicMock(return_value=False)
        old = MagicMock()
        old.status = "Concept"
        doc.get_doc_before_save = MagicMock(return_value=old)
        NixFactOfferte._stamp_portal_sent(doc)
        self.assertEqual(doc.portal_verstuurd_op, "2026-01-01 09:00:00")


if __name__ == "__main__":
    unittest.main()
