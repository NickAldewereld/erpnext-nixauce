"""Smoke tests for the MCP tool layer.

We don't spin up a real MCP runtime here — instead we call the underlying
async functions that `@mcp.tool()` decorated. FastMCP's decorator stores
the original callable so we can invoke it directly. If FastMCP changes
that contract, fall back to going through the registered tool registry.
"""

from __future__ import annotations

import json

import pytest
import respx

from nixfact_mcp import server


def _unwrap(tool_obj):
    """FastMCP tools may be either raw callables or wrappers with .fn / .func."""
    for attr in ("fn", "func", "__wrapped__"):
        inner = getattr(tool_obj, attr, None)
        if callable(inner):
            return inner
    if callable(tool_obj):
        return tool_obj
    raise TypeError(f"Cannot unwrap tool: {tool_obj!r}")


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    """Force a fresh client per test so respx mounts cleanly."""
    server._client = None
    yield
    server._client = None


@respx.mock
async def test_whoami_returns_user(base_url: str) -> None:
    respx.get(f"{base_url}/api/method/frappe.auth.get_logged_user").respond(
        200, json={"message": "nick@nixpay.nl"}
    )
    out = await _unwrap(server.whoami)()
    parsed = json.loads(out)
    assert parsed["base_url"] == base_url
    assert parsed["user"] == "nick@nixpay.nl"


@respx.mock
async def test_list_facturen_filters_and_ordering(base_url: str) -> None:
    route = respx.get(f"{base_url}/api/resource/NixFact Factuur").respond(
        200,
        json={
            "data": [
                {"name": "FAC-2026-00001", "status": "Verstuurd"},
                {"name": "FAC-2026-00002", "status": "Verstuurd"},
            ]
        },
    )
    out = await _unwrap(server.list_facturen)(
        status="Verstuurd",
        from_date="2026-01-01",
        limit_pages=1,
    )
    parsed = json.loads(out)
    assert parsed["status"] == "success"
    assert parsed["totalresults"] == 2
    assert parsed["facturen"][0]["name"] == "FAC-2026-00001"

    qs = dict(route.calls.last.request.url.params)
    filters = json.loads(qs["filters"])
    assert ["status", "=", "Verstuurd"] in filters
    assert ["factuur_datum", ">=", "2026-01-01"] in filters
    assert qs["order_by"] == "factuur_datum desc"


@respx.mock
async def test_create_offerte_routes_through_whitelisted_method(base_url: str) -> None:
    route = respx.post(
        f"{base_url}/api/method/nixfact_integration.api.create_offerte"
    ).respond(
        200,
        json={
            "message": {
                "success": True,
                "offerte_id": "OFF-2026-001",
                "offerte_nr": "OFF-2026-001",
            }
        },
    )
    payload = {
        "offerte_nr": "OFF-2026-001",
        "klant": "CUST-1",
        "bedrag_excl": 1000,
        "bedrag_incl": 1210,
        "offerte_datum": "2026-05-01",
    }
    out = await _unwrap(server.create_offerte)(offerte_data=payload)
    parsed = json.loads(out)
    assert parsed["success"] is True
    assert parsed["offerte_id"] == "OFF-2026-001"

    body = json.loads(route.calls.last.request.content)
    assert body == {"offerte_data": payload}


@respx.mock
async def test_update_offerte_status(base_url: str) -> None:
    respx.post(
        f"{base_url}/api/method/nixfact_integration.api.update_offerte_status"
    ).respond(200, json={"message": {"success": True, "new_status": "Geweigerd"}})
    out = await _unwrap(server.update_offerte_status)("OFF-1", "Geweigerd")
    parsed = json.loads(out)
    assert parsed["success"] is True
    assert parsed["new_status"] == "Geweigerd"


@respx.mock
async def test_get_btw_overzicht_uses_get(base_url: str) -> None:
    route = respx.get(
        f"{base_url}/api/method/nixfact_integration.api.statistieken.get_btw_overzicht"
    ).respond(
        200,
        json={
            "message": {
                "kwartaal": 2,
                "jaar": 2026,
                "verkoop_btw": 1000.0,
                "inkoop_btw": 200.0,
                "af_te_dragen": 800.0,
            }
        },
    )
    out = await _unwrap(server.get_btw_overzicht)(kwartaal=2, jaar=2026)
    parsed = json.loads(out)
    assert parsed["af_te_dragen"] == 800.0
    qs = dict(route.calls.last.request.url.params)
    assert qs == {"kwartaal": "2", "jaar": "2026"}


@respx.mock
async def test_attach_ubl(base_url: str) -> None:
    respx.post(
        f"{base_url}/api/method/nixfact_integration.api.ubl.attach_ubl_to_factuur"
    ).respond(
        200,
        json={
            "message": {
                "file_url": "/files/ubl/FAC-2026-00001.xml",
                "factuurnummer": "2026-00001",
            }
        },
    )
    out = await _unwrap(server.attach_ubl)("FAC-2026-00001")
    parsed = json.loads(out)
    assert parsed["file_url"].endswith(".xml")


@respx.mock
async def test_error_propagates_as_json(base_url: str) -> None:
    respx.get(f"{base_url}/api/resource/NixFact Factuur/NOPE").respond(
        404,
        json={
            "_server_messages": json.dumps(
                [json.dumps({"message": "Factuur NOPE niet gevonden"})]
            )
        },
    )
    out = await _unwrap(server.get_factuur)("NOPE")
    parsed = json.loads(out)
    assert parsed["status"] == "error"
    assert any("NOPE niet gevonden" in e for e in parsed["errors"])
    assert parsed["http_status"] == 404
