"""
Async HTTP client for the Frappe REST API used by Nixfact / ERPNext.

Frappe exposes two parallel APIs that we wrap here:

  * Resource API:  /api/resource/{DocType}[/{name}]
      CRUD on any DocType. List supports filters, fields, limit_start,
      limit_page_length, order_by.

  * Method API:    /api/method/{module.path.func}
      Whitelisted Python functions. Args go in the JSON body (POST) or
      querystring (GET). Return value is wrapped as {"message": ...}.

Auth is a single header:
    Authorization: token {api_key}:{api_secret}

API keys are generated per-user under "API Access" on the Frappe user form.

This client is intentionally low-level. It does not model individual
DocTypes — that is left to the higher-level MCP tool layer (and to
`nixfact_resource_*` / `nixfact_method` for ad-hoc calls). This keeps
the surface area small and lets us add conveniences only where they
earn their keep.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
DEFAULT_USER_AGENT = (
    "nixfact-mcp/0.1.0 (+https://github.com/NickAldewereld/erpnext-nixauce)"
)


class NixfactError(Exception):
    """Raised when Frappe returns a non-2xx response or a structured error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        payload: Any = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class NixfactClient:
    """Async client for the Nixfact (Frappe) REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        max_retries: int = 2,
    ) -> None:
        self.base_url = (base_url or os.environ.get("NIXFACT_BASE_URL", "")).rstrip("/")
        if not self.base_url:
            raise ValueError(
                "No Nixfact base URL provided. Set NIXFACT_BASE_URL env var "
                "(e.g. https://erp.example.com) or pass base_url to NixfactClient."
            )
        self.api_key = api_key or os.environ.get("NIXFACT_API_KEY")
        self.api_secret = api_secret or os.environ.get("NIXFACT_API_SECRET")
        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Nixfact API credentials missing. Set NIXFACT_API_KEY and "
                "NIXFACT_API_SECRET env vars, or pass them to NixfactClient."
            )
        self.timeout = timeout
        self.user_agent = user_agent
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "NixfactClient":
        self._client = self._build_client()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.close()

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "User-Agent": self.user_agent,
                "Authorization": f"token {self.api_key}:{self.api_secret}",
                "Accept": "application/json",
            },
        )

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> Any:
        client = self._ensure_client()
        url = path if path.startswith("/") else f"/{path}"
        encoded_params = _encode_query_params(params) if params else None

        attempt = 0
        last_exc: Exception | None = None
        resp: httpx.Response | None = None
        while attempt <= self.max_retries:
            try:
                resp = await client.request(
                    method,
                    url,
                    params=encoded_params,
                    json=json_body,
                )
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                break
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                last_exc = e
                attempt += 1
                if attempt > self.max_retries:
                    raise
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
        else:  # pragma: no cover
            assert last_exc is not None
            raise last_exc

        assert resp is not None

        if resp.status_code >= 400:
            payload: Any
            try:
                payload = resp.json()
            except ValueError:
                payload = resp.text
            msg = _extract_frappe_error(payload) or f"Frappe HTTP {resp.status_code}"
            logger.warning("Nixfact error: %s %s -> %s", method, url, msg)
            raise NixfactError(msg, status_code=resp.status_code, payload=payload)

        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError as e:
            raise NixfactError(
                f"Invalid JSON in Nixfact response: {e}", status_code=resp.status_code
            ) from e

    # -- Resource API ------------------------------------------------------

    async def list_resource(
        self,
        doctype: str,
        *,
        filters: list[list[Any]] | dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit_start: int = 0,
        limit_page_length: int = 20,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """Single page of `list` results for `doctype`."""
        params: dict[str, Any] = {
            "limit_start": limit_start,
            "limit_page_length": limit_page_length,
        }
        if filters:
            params["filters"] = filters
        if fields:
            params["fields"] = fields
        if order_by:
            params["order_by"] = order_by
        data = await self._request("GET", f"/api/resource/{doctype}", params=params)
        if isinstance(data, dict):
            return list(data.get("data") or [])
        if isinstance(data, list):
            return data
        return []

    async def list_resource_all(
        self,
        doctype: str,
        *,
        filters: list[list[Any]] | dict[str, Any] | None = None,
        fields: list[str] | None = None,
        page_size: int = 100,
        max_pages: int = 1000,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """Iterate `list` pages and return all rows."""
        items: list[dict[str, Any]] = []
        offset = 0
        for _ in range(max_pages):
            page = await self.list_resource(
                doctype,
                filters=filters,
                fields=fields,
                limit_start=offset,
                limit_page_length=page_size,
                order_by=order_by,
            )
            if not page:
                break
            items.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return items

    async def get_resource(self, doctype: str, name: str) -> dict[str, Any]:
        """Fetch a single document by name (primary key)."""
        data = await self._request("GET", f"/api/resource/{doctype}/{name}")
        if isinstance(data, dict):
            return data.get("data") or data
        return {"data": data}

    async def create_resource(
        self, doctype: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a new document."""
        data = await self._request(
            "POST", f"/api/resource/{doctype}", json_body=fields
        )
        if isinstance(data, dict):
            return data.get("data") or data
        return {"data": data}

    async def update_resource(
        self, doctype: str, name: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing document. Only fields you provide are changed."""
        data = await self._request(
            "PUT", f"/api/resource/{doctype}/{name}", json_body=fields
        )
        if isinstance(data, dict):
            return data.get("data") or data
        return {"data": data}

    async def delete_resource(self, doctype: str, name: str) -> dict[str, Any]:
        """Delete a document. Use with care."""
        data = await self._request("DELETE", f"/api/resource/{doctype}/{name}")
        if isinstance(data, dict):
            return data
        return {"deleted": name}

    # -- Method API --------------------------------------------------------

    async def call_method(
        self,
        method: str,
        *,
        params: dict[str, Any] | None = None,
        http_method: str = "POST",
    ) -> Any:
        """Call any whitelisted Frappe method. Returns the unwrapped `message`."""
        if http_method.upper() == "GET":
            data = await self._request(
                "GET", f"/api/method/{method}", params=params
            )
        else:
            data = await self._request(
                "POST", f"/api/method/{method}", json_body=params
            )
        if isinstance(data, dict) and "message" in data:
            return data["message"]
        return data

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def _encode_query_params(params: dict[str, Any]) -> dict[str, str]:
    """Frappe expects list/dict querystring values to be JSON-encoded."""
    encoded: dict[str, str] = {}
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, (list, dict)):
            encoded[k] = json.dumps(v)
        elif isinstance(v, bool):
            encoded[k] = "1" if v else "0"
        else:
            encoded[k] = str(v)
    return encoded


def _extract_frappe_error(payload: Any) -> str | None:
    """Pull a human message out of one of Frappe's many error shapes."""
    if isinstance(payload, dict):
        for key in ("_server_messages", "exception", "exc", "message"):
            v = payload.get(key)
            if not v:
                continue
            if isinstance(v, str):
                try:
                    decoded = json.loads(v)
                except (ValueError, TypeError):
                    return v
                if isinstance(decoded, list) and decoded:
                    return _coerce_msg(decoded[0])
                return _coerce_msg(decoded)
            return _coerce_msg(v)
        return None
    if isinstance(payload, str):
        return payload
    return None


def _coerce_msg(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get("message") or v)
    return str(v)
