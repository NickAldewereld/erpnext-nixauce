# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de WeFact REST-client met een neppe transport."""

import unittest


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _BadJsonResponse:
    status_code = 200

    def json(self):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


class _FakeTransport:
    """Verzamelt requests en geeft vooraf bepaalde antwoorden terug."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, url, json, timeout=None):
        self.calls.append(json)
        return _FakeResponse(self._responses.pop(0))


class TestRequest(unittest.TestCase):

    def _client(self, responses):
        from nixfact_integration.wefact_sync.client import WeFactClient

        transport = _FakeTransport(responses)
        return WeFactClient(api_key="KEY", transport=transport), transport

    def test_api_key_en_controller_in_body(self):
        client, t = self._client([{"status": "success"}])
        client.request("debtor", "list")
        self.assertEqual(t.calls[0]["api_key"], "KEY")
        self.assertEqual(t.calls[0]["controller"], "debtor")
        self.assertEqual(t.calls[0]["action"], "list")

    def test_list_all_pagineert_tot_leeg(self):
        # Pagina 1: 100 debtors, pagina 2: 5, pagina 3: 0 → stopt.
        p1 = {"status": "success", "debtors": [{"i": i} for i in range(100)]}
        p2 = {"status": "success", "debtors": [{"i": i} for i in range(5)]}
        p3 = {"status": "success", "debtors": []}
        client, t = self._client([p1, p2, p3])
        items = client.list_all("debtor")
        self.assertEqual(len(items), 105)
        self.assertEqual(t.calls[0]["offset"], 0)
        self.assertEqual(t.calls[1]["offset"], 100)

    def test_show_gebruikt_id_field(self):
        client, t = self._client([{"status": "success", "invoice": {"x": 1}}])
        client.show("invoice", "F0001", "InvoiceCode")
        self.assertEqual(t.calls[0]["action"], "show")
        self.assertEqual(t.calls[0]["InvoiceCode"], "F0001")

    def test_modified_since_param(self):
        client, t = self._client([{"status": "success", "debtors": []}])
        client.list_all("debtor", params={"modified": "2026-07-01 00:00:00"})
        self.assertEqual(t.calls[0]["modified"], "2026-07-01 00:00:00")

    def test_list_all_stopt_bij_totalresults_in_een_call(self):
        # WeFact geeft alles in één call terug met totalresults; niet
        # blijven doorpagineren over overlappende vensters.
        page = {"status": "success", "totalresults": 3,
                "invoices": [{"i": 0}, {"i": 1}, {"i": 2}]}
        client, t = self._client([page])
        items = client.list_all("invoice")
        self.assertEqual(len(items), 3)
        self.assertEqual(len(t.calls), 1)

    def test_niet_json_wordt_geretried(self):
        from unittest import mock
        from nixfact_integration.wefact_sync.client import WeFactClient

        class _T:
            def __init__(self):
                self.n = 0
            def __call__(self, url, json, timeout=None):
                self.n += 1
                if self.n == 1:
                    return _BadJsonResponse()
                return _FakeResponse({"status": "success", "debtors": []})

        t = _T()
        client = WeFactClient(api_key="K", transport=t)
        with mock.patch("nixfact_integration.wefact_sync.client.time.sleep"):
            client.request("debtor", "list")
        self.assertEqual(t.n, 2)  # eerste niet-JSON, tweede gelukt


if __name__ == "__main__":
    unittest.main()
