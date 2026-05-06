# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

import unittest
from unittest.mock import MagicMock, patch


class TestPortalContext(unittest.TestCase):
    def test_missing_token_raises_permission_error(self):
        from nixfact_integration.www import offerte as portal
        with patch.object(portal, "frappe") as f:
            f.form_dict = {}

            class _PE(Exception):
                pass

            f.PermissionError = _PE
            f.throw.side_effect = lambda msg, exc=_PE: (_ for _ in ()).throw(exc(msg))
            with self.assertRaises(_PE):
                portal.get_context(MagicMock())

    def test_unknown_token_raises_does_not_exist(self):
        from nixfact_integration.www import offerte as portal
        with patch.object(portal, "frappe") as f:
            f.form_dict = {"token": "deadbeef"}
            f.db.get_value.return_value = None

            class _DNE(Exception):
                pass

            f.DoesNotExistError = _DNE
            f.throw.side_effect = lambda msg, exc=_DNE: (_ for _ in ()).throw(exc(msg))
            with self.assertRaises(_DNE):
                portal.get_context(MagicMock())
