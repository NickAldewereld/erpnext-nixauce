# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de pure cursor-helper."""

import unittest

from nixfact_integration.wefact_sync.cursor import max_modified


class TestMaxModified(unittest.TestCase):

    def test_hoogste(self):
        recs = [{"Modified": "2026-07-01 10:00:00"},
                {"Modified": "2026-07-05 09:00:00"},
                {"Modified": "2026-07-03 12:00:00"}]
        self.assertEqual(max_modified(recs), "2026-07-05 09:00:00")

    def test_lege_modified_genegeerd(self):
        recs = [{"Modified": ""}, {"Modified": "2026-07-02 08:00:00"}]
        self.assertEqual(max_modified(recs), "2026-07-02 08:00:00")

    def test_geen_records(self):
        self.assertEqual(max_modified([]), "")


if __name__ == "__main__":
    unittest.main()
