"""Tests for NixfactClient against a respx-mocked Frappe."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from nixfact_mcp.client import (
    NixfactClient,
    NixfactError,
    _encode_query_params,
    _extract_frappe_error,
)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_init_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIXFACT_BASE_URL", "https://erp.test/")
    monkeypatch.setenv("NIXFACT_API_KEY", "k")
    monkeypatch.setenv("NIXFACT_API_SECRET", "s")
    c = NixfactClient()
    assert c.base_url == "https://erp.test"  # trailing slash stripped
    assert c.api_key == "k"
    assert c.api_secret == "s"


def test_init_missing_base_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NIXFACT_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="base URL"):
        NixfactClient(api_key="k", api_secret="s")


def test_init_missing_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NIXFACT_API_KEY", raising=False)
    monkeypatch.delenv("NIXFACT_API_SECRET", raising=False)
    with pytest.raises(ValueError, match="credentials"):
        NixfactClient(base_url="https://erp.test")


# ---------------------------------------------------------------------------
# Query encoding helpers (pure-function tests, no HTTP)
# ---------------------------------------------------------------------------


def test_encode_query_params_lists_become_json() -> None:
    out = _encode_query_params(
        {
            "filters": [["status", "=", "Verstuurd"]],
            "fields": ["name", "factuurnummer"],
            "limit_start": 0,
            "limit_page_length": 50,
        }
    )
    assert json.loads(out["filters"]) == [["status", "=", "Verstuurd"]]
    assert json.loads(out["fields"]) == ["name", "factuurnummer"]
    assert out["limit_start"] == "0"
    assert out["limit_page_length"] == "50"


def test_encode_query_params_drops_none() -> None:
    out = _encode_query_params({"a": None, "b": "x"})
    assert "a" not in out
    assert out["b"] == "x"


def test_encode_query_params_bool_to_one_zero() -> None:
    out = _encode_query_params({"flag_on": True, "flag_off": False})
    assert out["flag_on"] == "1"
    assert out["flag_off"] == "0"


def test_extract_frappe_error_server_messages() -> None:
    payload = {
        "_server_messages": json.dumps(
            [json.dumps({"message": "Not allowed: insufficient permissions"})]
        )
    }
    msg = _extract_frappe_error(payload)
    assert msg is not None
    assert "Not allowed" in msg


def test_extract_frappe_error_plain_string() -> None:
    assert _extract_frappe_error({"message": "boom"}) == "boom"


def test_extract_frappe_error_text_payload() -> None:
    assert _extract_frappe_error("html error page") == "html error page"


# ---------------------------------------------------------------------------
# Auth header
# ---------------------------------------------------------------------------


@respx.mock
async def test_auth_header_present(base_url: str) -> None:
    route = respx.get(f"{base_url}/api/resource/Customer").respond(
        200, json={"data": []}
    )
    async with NixfactClient() as c:
        await c.list_resource("Customer")
    assert route.called
    req = route.calls.last.request
    assert req.headers["Authorization"] == "token test-key:test-secret"
    assert req.headers["Accept"] == "application/json"


# ---------------------------------------------------------------------------
# Resource API
# ---------------------------------------------------------------------------


@respx.mock
async def test_list_resource_encodes_filters(base_url: str) -> None:
    route = respx.get(f"{base_url}/api/resource/NixFact Factuur").respond(
        200,
        json={
            "data": [
                {"name": "FAC-2026-00001", "factuurnummer": "2026-00001"},
            ]
        },
    )
    async with NixfactClient() as c:
        rows = await c.list_resource(
            "NixFact Factuur",
            filters=[["status", "=", "Verstuurd"]],
            fields=["name", "factuurnummer"],
            limit_start=0,
            limit_page_length=50,
            order_by="modified desc",
        )
    assert rows == [{"name": "FAC-2026-00001", "factuurnummer": "2026-00001"}]
    assert route.called
    qs = dict(route.calls.last.request.url.params)
    assert json.loads(qs["filters"]) == [["status", "=", "Verstuurd"]]
    assert json.loads(qs["fields"]) == ["name", "factuurnummer"]
    assert qs["limit_start"] == "0"
    assert qs["limit_page_length"] == "50"
    assert qs["order_by"] == "modified desc"


@respx.mock
async def test_list_resource_all_paginates(base_url: str) -> None:
    page1 = [{"name": f"FAC-{i:05d}"} for i in range(100)]
    page2 = [{"name": f"FAC-{i:05d}"} for i in range(100, 142)]

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("limit_start", "0"))
        if offset == 0:
            return httpx.Response(200, json={"data": page1})
        if offset == 100:
            return httpx.Response(200, json={"data": page2})
        return httpx.Response(200, json={"data": []})

    respx.get(f"{base_url}/api/resource/NixFact Factuur").mock(side_effect=handler)
    async with NixfactClient() as c:
        rows = await c.list_resource_all("NixFact Factuur", page_size=100)
    assert len(rows) == 142
    assert rows[0]["name"] == "FAC-00000"
    assert rows[-1]["name"] == "FAC-00141"


@respx.mock
async def test_get_resource_unwraps_data(base_url: str) -> None:
    respx.get(f"{base_url}/api/resource/NixFact Factuur/FAC-1").respond(
        200, json={"data": {"name": "FAC-1", "status": "Betaald"}}
    )
    async with NixfactClient() as c:
        doc = await c.get_resource("NixFact Factuur", "FAC-1")
    assert doc == {"name": "FAC-1", "status": "Betaald"}


@respx.mock
async def test_create_resource_posts_body(base_url: str) -> None:
    route = respx.post(f"{base_url}/api/resource/NixFact Offerte").respond(
        200,
        json={
            "data": {
                "name": "OFF-1",
                "offerte_nr": "OFF-1",
                "klant": "CUST-1",
                "status": "Geaccepteerd",
            }
        },
    )
    body = {
        "offerte_nr": "OFF-1",
        "klant": "CUST-1",
        "bedrag_excl": 100,
        "bedrag_incl": 121,
        "offerte_datum": "2026-05-01",
    }
    async with NixfactClient() as c:
        doc = await c.create_resource("NixFact Offerte", body)
    assert doc["status"] == "Geaccepteerd"
    sent = json.loads(route.calls.last.request.content)
    assert sent == body


@respx.mock
async def test_update_resource_uses_put(base_url: str) -> None:
    route = respx.put(f"{base_url}/api/resource/NixFact Offerte/OFF-1").respond(
        200, json={"data": {"name": "OFF-1", "status": "Geweigerd"}}
    )
    async with NixfactClient() as c:
        doc = await c.update_resource("NixFact Offerte", "OFF-1", {"status": "Geweigerd"})
    assert doc["status"] == "Geweigerd"
    assert route.called
    assert json.loads(route.calls.last.request.content) == {"status": "Geweigerd"}


@respx.mock
async def test_delete_resource(base_url: str) -> None:
    route = respx.delete(f"{base_url}/api/resource/NixFact Offerte/OFF-1").respond(
        200, json={"message": "ok"}
    )
    async with NixfactClient() as c:
        out = await c.delete_resource("NixFact Offerte", "OFF-1")
    assert route.called
    assert out  # dict returned


# ---------------------------------------------------------------------------
# Method API
# ---------------------------------------------------------------------------


@respx.mock
async def test_call_method_post_unwraps_message(base_url: str) -> None:
    route = respx.post(
        f"{base_url}/api/method/nixfact_integration.api.create_offerte"
    ).respond(
        200,
        json={"message": {"success": True, "offerte_id": "OFF-1"}},
    )
    async with NixfactClient() as c:
        result = await c.call_method(
            "nixfact_integration.api.create_offerte",
            params={"offerte_data": {"offerte_nr": "OFF-1"}},
        )
    assert result == {"success": True, "offerte_id": "OFF-1"}
    body = json.loads(route.calls.last.request.content)
    assert body == {"offerte_data": {"offerte_nr": "OFF-1"}}


@respx.mock
async def test_call_method_get_uses_querystring(base_url: str) -> None:
    route = respx.get(
        f"{base_url}/api/method/nixfact_integration.api.statistieken.get_btw_overzicht"
    ).respond(200, json={"message": {"af_te_dragen": 42.0}})
    async with NixfactClient() as c:
        result = await c.call_method(
            "nixfact_integration.api.statistieken.get_btw_overzicht",
            params={"kwartaal": 2, "jaar": 2026},
            http_method="GET",
        )
    assert result == {"af_te_dragen": 42.0}
    qs = dict(route.calls.last.request.url.params)
    assert qs == {"kwartaal": "2", "jaar": "2026"}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@respx.mock
async def test_400_extracts_server_messages(base_url: str) -> None:
    payload = {
        "_server_messages": json.dumps(
            [json.dumps({"message": "Klant CUST-99 bestaat niet"})]
        )
    }
    respx.get(f"{base_url}/api/resource/Customer/CUST-99").respond(404, json=payload)
    async with NixfactClient() as c:
        with pytest.raises(NixfactError) as ei:
            await c.get_resource("Customer", "CUST-99")
    assert "bestaat niet" in str(ei.value)
    assert ei.value.status_code == 404


@respx.mock
async def test_500_retries_then_succeeds(base_url: str) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"data": [{"name": "x"}]})

    respx.get(f"{base_url}/api/resource/Customer").mock(side_effect=handler)
    async with NixfactClient() as c:
        rows = await c.list_resource("Customer")
    assert rows == [{"name": "x"}]
    assert calls["n"] == 3


@respx.mock
async def test_500_exhausts_retries(base_url: str) -> None:
    respx.get(f"{base_url}/api/resource/Customer").respond(500, text="still broken")
    async with NixfactClient() as c:
        with pytest.raises(httpx.HTTPStatusError):
            await c.list_resource("Customer")
