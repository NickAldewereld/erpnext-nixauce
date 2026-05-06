"""
Nixfact MCP server.

Exposes a Nixfact / ERPNext (Frappe-based) instance as MCP tools so any
MCP-compatible client (Claude Desktop, Claude Code, Cursor, …) can read
and modify a Nixfact administration.

Design notes:
  * The thin layer is `nixfact_method` and `nixfact_resource_*`, which
    let you call any whitelisted Frappe method or any DocType CRUD —
    useful for endpoints we haven't wrapped yet, and as a safety valve
    when Nixfact ships new ones.
  * Higher-level tools wrap the most common operations on Nixfact's
    DocTypes (klanten/customers, facturen, offertes, abonnementen,
    inkoopfacturen, bank transacties) and on Nixfact's whitelisted
    helpers (UBL, Mollie, Ponto, statistieken). Field names match the
    Nixfact DocType definitions verbatim — Dutch where Nixfact is Dutch.
  * Pagination: `list_*` tools fetch all pages by default. Pass
    `limit_pages=1` if you only want the first page.
  * Filtering: most list tools take a `modified_since` parameter for
    incremental sync, mapped to Frappe's `modified` field.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp.server.fastmcp import FastMCP

from .client import NixfactClient, NixfactError

logger = logging.getLogger("nixfact-mcp")

# Single client instance for the lifetime of the server. Created lazily
# on first use so importing this module (e.g. for tests) doesn't require
# NIXFACT_BASE_URL/KEY/SECRET to be set.
_client: NixfactClient | None = None


@asynccontextmanager
async def _lifespan(_server: FastMCP) -> AsyncIterator[None]:
    global _client
    try:
        yield
    finally:
        if _client is not None:
            await _client.close()
            _client = None


mcp = FastMCP(
    "nixfact",
    instructions=(
        "Tools for reading and modifying a Nixfact administration via the "
        "Frappe REST API. Use `nixfact_method` for any whitelisted method "
        "and `nixfact_resource_list/get/create/update` for CRUD on any "
        "DocType not covered by a dedicated tool. Field names follow the "
        "Nixfact DocType definitions (Dutch where Nixfact is Dutch)."
    ),
    lifespan=_lifespan,
)


def _get_client() -> NixfactClient:
    global _client
    if _client is None:
        _client = NixfactClient()
    return _client


def _result(data: Any) -> str:
    """Serialise tool output as JSON string (MCP returns text)."""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _err(e: NixfactError) -> str:
    return _result(
        {"status": "error", "errors": [str(e)], "http_status": e.status_code}
    )


def _modified_filter(modified_since: str | None) -> list[list[Any]] | None:
    if not modified_since:
        return None
    return [["modified", ">=", modified_since]]


# --------------------------------------------------------------------------
# Generic escape hatches
# --------------------------------------------------------------------------


@mcp.tool()
async def nixfact_method(
    method: str,
    params: dict[str, Any] | None = None,
    http_method: str = "POST",
) -> str:
    """Call any whitelisted Frappe method directly.

    Use this for endpoints not covered by the dedicated tools below, or
    to pass parameters that the dedicated tools don't expose.

    Args:
        method: Fully-qualified dotted path, e.g.
            "nixfact_integration.api.bank.sync_ponto_transactions".
        params: Args to pass as a dict.
        http_method: "GET" or "POST" (default POST).

    Returns:
        JSON-encoded `message` value from the Frappe response.
    """
    client = _get_client()
    try:
        data = await client.call_method(method, params=params, http_method=http_method)
    except NixfactError as e:
        return _err(e)
    return _result(data)


@mcp.tool()
async def nixfact_resource_list(
    doctype: str,
    filters: list[list[Any]] | dict[str, Any] | None = None,
    fields: list[str] | None = None,
    order_by: str | None = None,
    limit_pages: int | None = None,
) -> str:
    """List rows of any DocType.

    Args:
        doctype: e.g. "Customer", "NixFact Factuur", "NixFact Offerte".
        filters: Frappe-style filter list, e.g.
            [["status","=","Verstuurd"],["factuur_datum",">=","2026-01-01"]].
        fields: Columns to return, e.g. ["name","factuurnummer","status"].
            Defaults to ["name"] when omitted (Frappe default).
        order_by: e.g. "modified desc".
        limit_pages: 1 for the first page only, otherwise all pages.
    """
    client = _get_client()
    try:
        if limit_pages == 1:
            data = await client.list_resource(
                doctype,
                filters=filters,
                fields=fields,
                order_by=order_by,
                limit_page_length=100,
            )
            return _result({"status": "success", "totalresults": len(data), "data": data})
        items = await client.list_resource_all(
            doctype,
            filters=filters,
            fields=fields,
            order_by=order_by,
            max_pages=limit_pages or 1000,
        )
    except NixfactError as e:
        return _err(e)
    return _result({"status": "success", "totalresults": len(items), "data": items})


@mcp.tool()
async def nixfact_resource_get(doctype: str, name: str) -> str:
    """Fetch a single document by `name` (the Frappe primary key).

    Args:
        doctype: e.g. "NixFact Factuur".
        name: e.g. "FAC-2026-00001".
    """
    client = _get_client()
    try:
        data = await client.get_resource(doctype, name)
    except NixfactError as e:
        return _err(e)
    return _result(data)


@mcp.tool()
async def nixfact_resource_create(doctype: str, fields: dict[str, Any]) -> str:
    """Create a new document of any DocType."""
    client = _get_client()
    try:
        data = await client.create_resource(doctype, fields)
    except NixfactError as e:
        return _err(e)
    return _result(data)


@mcp.tool()
async def nixfact_resource_update(
    doctype: str, name: str, fields: dict[str, Any]
) -> str:
    """Update an existing document. Only fields you provide are changed."""
    client = _get_client()
    try:
        data = await client.update_resource(doctype, name, fields)
    except NixfactError as e:
        return _err(e)
    return _result(data)


# --------------------------------------------------------------------------
# Klanten (ERPNext built-in Customer)
# --------------------------------------------------------------------------


@mcp.tool()
async def list_klanten(
    search_for: str | None = None,
    modified_since: str | None = None,
    limit_pages: int | None = None,
) -> str:
    """List customers (ERPNext built-in `Customer` DocType).

    Args:
        search_for: Substring match on customer_name. Optional.
        modified_since: ISO date for incremental sync.
        limit_pages: 1 for first page only.
    """
    filters: list[list[Any]] = []
    if search_for:
        filters.append(["customer_name", "like", f"%{search_for}%"])
    mod = _modified_filter(modified_since)
    if mod:
        filters.extend(mod)
    fields = [
        "name",
        "customer_name",
        "customer_type",
        "customer_group",
        "tax_id",
        "email_id",
        "mobile_no",
        "modified",
    ]
    client = _get_client()
    try:
        if limit_pages == 1:
            items = await client.list_resource(
                "Customer",
                filters=filters or None,
                fields=fields,
                limit_page_length=100,
                order_by="modified desc",
            )
        else:
            items = await client.list_resource_all(
                "Customer",
                filters=filters or None,
                fields=fields,
                max_pages=limit_pages or 1000,
                order_by="modified desc",
            )
    except NixfactError as e:
        return _err(e)
    return _result({"status": "success", "totalresults": len(items), "klanten": items})


@mcp.tool()
async def get_klant(name: str) -> str:
    """Fetch a single customer by `name` (e.g. "CUST-0001")."""
    client = _get_client()
    try:
        data = await client.get_resource("Customer", name)
    except NixfactError as e:
        return _err(e)
    return _result(data)


# --------------------------------------------------------------------------
# Facturen (NixFact Factuur — sales invoices)
# --------------------------------------------------------------------------

_FACTUUR_FIELDS = [
    "name",
    "factuurnummer",
    "klant",
    "klant_naam",
    "factuur_datum",
    "vervaldatum",
    "bedrag_excl_btw",
    "btw_bedrag",
    "bedrag_incl_btw",
    "openstaand_bedrag",
    "status",
    "modified",
]


@mcp.tool()
async def list_facturen(
    status: str | None = None,
    klant: str | None = None,
    modified_since: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit_pages: int | None = None,
) -> str:
    """List sales invoices (NixFact Factuur).

    Args:
        status: e.g. "Concept", "Verstuurd", "Betaald", "Herinnering verstuurd",
            "Aanmaning verstuurd", "Geannuleerd".
        klant: Filter to a specific customer (name, e.g. "CUST-0001").
        modified_since: ISO date for incremental sync.
        from_date: factuur_datum >= this ISO date.
        to_date: factuur_datum <= this ISO date.
        limit_pages: 1 for first page only.
    """
    filters: list[list[Any]] = []
    if status:
        filters.append(["status", "=", status])
    if klant:
        filters.append(["klant", "=", klant])
    if from_date:
        filters.append(["factuur_datum", ">=", from_date])
    if to_date:
        filters.append(["factuur_datum", "<=", to_date])
    mod = _modified_filter(modified_since)
    if mod:
        filters.extend(mod)
    client = _get_client()
    try:
        if limit_pages == 1:
            items = await client.list_resource(
                "NixFact Factuur",
                filters=filters or None,
                fields=_FACTUUR_FIELDS,
                limit_page_length=100,
                order_by="factuur_datum desc",
            )
        else:
            items = await client.list_resource_all(
                "NixFact Factuur",
                filters=filters or None,
                fields=_FACTUUR_FIELDS,
                max_pages=limit_pages or 1000,
                order_by="factuur_datum desc",
            )
    except NixfactError as e:
        return _err(e)
    return _result({"status": "success", "totalresults": len(items), "facturen": items})


@mcp.tool()
async def get_factuur(name: str) -> str:
    """Fetch a single invoice by `name` (e.g. "FAC-2026-00001")."""
    client = _get_client()
    try:
        data = await client.get_resource("NixFact Factuur", name)
    except NixfactError as e:
        return _err(e)
    return _result(data)


@mcp.tool()
async def create_factuur(fields: dict[str, Any]) -> str:
    """Create a new NixFact Factuur (sales invoice).

    Args:
        fields: Dict matching the NixFact Factuur DocType. Common fields:
            klant (Customer name), factuur_datum (YYYY-MM-DD), vervaldatum,
            referentie, regels (child table list of dicts with omschrijving,
            aantal, prijs_per_stuk, btw_percentage, ...).
    """
    client = _get_client()
    try:
        data = await client.create_resource("NixFact Factuur", fields)
    except NixfactError as e:
        return _err(e)
    return _result(data)


@mcp.tool()
async def update_factuur(name: str, fields: dict[str, Any]) -> str:
    """Update an existing invoice. Only fields you provide are changed."""
    client = _get_client()
    try:
        data = await client.update_resource("NixFact Factuur", name, fields)
    except NixfactError as e:
        return _err(e)
    return _result(data)


# --------------------------------------------------------------------------
# Offertes (NixFact Offerte) — uses whitelisted helpers where they exist
# --------------------------------------------------------------------------


@mcp.tool()
async def list_offertes(
    status: str | None = None,
    klant: str | None = None,
    modified_since: str | None = None,
    limit_pages: int | None = None,
) -> str:
    """List quotes (NixFact Offerte).

    Args:
        status: e.g. "Geaccepteerd", "Geweigerd", "Factuur aangemaakt".
        klant: Filter to a specific customer.
        modified_since: ISO date for incremental sync.
        limit_pages: 1 for first page only.
    """
    filters: list[list[Any]] = []
    if status:
        filters.append(["status", "=", status])
    if klant:
        filters.append(["klant", "=", klant])
    mod = _modified_filter(modified_since)
    if mod:
        filters.extend(mod)
    fields = [
        "name",
        "offerte_nr",
        "klant",
        "bedrag_excl",
        "bedrag_incl",
        "offerte_datum",
        "referentie",
        "status",
        "modified",
    ]
    client = _get_client()
    try:
        if limit_pages == 1:
            items = await client.list_resource(
                "NixFact Offerte",
                filters=filters or None,
                fields=fields,
                limit_page_length=100,
                order_by="offerte_datum desc",
            )
        else:
            items = await client.list_resource_all(
                "NixFact Offerte",
                filters=filters or None,
                fields=fields,
                max_pages=limit_pages or 1000,
                order_by="offerte_datum desc",
            )
    except NixfactError as e:
        return _err(e)
    return _result({"status": "success", "totalresults": len(items), "offertes": items})


@mcp.tool()
async def get_offerte(offerte_id: str) -> str:
    """Fetch a single offerte. Wraps `nixfact_integration.api.get_offerte`."""
    client = _get_client()
    try:
        data = await client.call_method(
            "nixfact_integration.api.get_offerte",
            params={"offerte_id": offerte_id},
        )
    except NixfactError as e:
        return _err(e)
    return _result(data)


@mcp.tool()
async def create_offerte(offerte_data: dict[str, Any]) -> str:
    """Create a new offerte. Wraps `nixfact_integration.api.create_offerte`.

    Args:
        offerte_data: dict with offerte_nr, klant, bedrag_excl, bedrag_incl,
            offerte_datum (YYYY-MM-DD), and optional referentie / status.
    """
    client = _get_client()
    try:
        data = await client.call_method(
            "nixfact_integration.api.create_offerte",
            params={"offerte_data": offerte_data},
        )
    except NixfactError as e:
        return _err(e)
    return _result(data)


@mcp.tool()
async def update_offerte_status(offerte_id: str, status: str) -> str:
    """Update an offerte's status to one of:
    Geaccepteerd / Geweigerd / Factuur aangemaakt.
    """
    client = _get_client()
    try:
        data = await client.call_method(
            "nixfact_integration.api.update_offerte_status",
            params={"offerte_id": offerte_id, "status": status},
        )
    except NixfactError as e:
        return _err(e)
    return _result(data)


# --------------------------------------------------------------------------
# Abonnementen (NixFact Abonnement)
# --------------------------------------------------------------------------


@mcp.tool()
async def list_abonnementen(
    klant: str | None = None,
    status: str | None = None,
    modified_since: str | None = None,
    limit_pages: int | None = None,
) -> str:
    """List subscriptions (NixFact Abonnement)."""
    filters: list[list[Any]] = []
    if klant:
        filters.append(["klant", "=", klant])
    if status:
        filters.append(["status", "=", status])
    mod = _modified_filter(modified_since)
    if mod:
        filters.extend(mod)
    client = _get_client()
    try:
        if limit_pages == 1:
            items = await client.list_resource(
                "NixFact Abonnement",
                filters=filters or None,
                fields=["*"],
                limit_page_length=100,
                order_by="modified desc",
            )
        else:
            items = await client.list_resource_all(
                "NixFact Abonnement",
                filters=filters or None,
                fields=["*"],
                max_pages=limit_pages or 1000,
                order_by="modified desc",
            )
    except NixfactError as e:
        return _err(e)
    return _result(
        {"status": "success", "totalresults": len(items), "abonnementen": items}
    )


@mcp.tool()
async def get_abonnement(name: str) -> str:
    """Fetch a single subscription by `name`."""
    client = _get_client()
    try:
        data = await client.get_resource("NixFact Abonnement", name)
    except NixfactError as e:
        return _err(e)
    return _result(data)


# --------------------------------------------------------------------------
# Inkoopfacturen (NixFact Inkoopfactuur — purchase invoices)
# --------------------------------------------------------------------------


@mcp.tool()
async def list_inkoopfacturen(
    leverancier: str | None = None,
    kostencategorie: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    modified_since: str | None = None,
    limit_pages: int | None = None,
) -> str:
    """List purchase invoices (NixFact Inkoopfactuur)."""
    filters: list[list[Any]] = []
    if leverancier:
        filters.append(["leverancier", "=", leverancier])
    if kostencategorie:
        filters.append(["kostencategorie", "=", kostencategorie])
    if from_date:
        filters.append(["factuurdatum", ">=", from_date])
    if to_date:
        filters.append(["factuurdatum", "<=", to_date])
    mod = _modified_filter(modified_since)
    if mod:
        filters.extend(mod)
    fields = [
        "name",
        "leverancier",
        "factuurnummer",
        "factuurdatum",
        "bedrag_excl",
        "btw_bedrag",
        "bedrag_incl",
        "kostencategorie",
        "modified",
    ]
    client = _get_client()
    try:
        if limit_pages == 1:
            items = await client.list_resource(
                "NixFact Inkoopfactuur",
                filters=filters or None,
                fields=fields,
                limit_page_length=100,
                order_by="factuurdatum desc",
            )
        else:
            items = await client.list_resource_all(
                "NixFact Inkoopfactuur",
                filters=filters or None,
                fields=fields,
                max_pages=limit_pages or 1000,
                order_by="factuurdatum desc",
            )
    except NixfactError as e:
        return _err(e)
    return _result(
        {"status": "success", "totalresults": len(items), "inkoopfacturen": items}
    )


@mcp.tool()
async def get_inkoopfactuur(name: str) -> str:
    """Fetch a single purchase invoice by `name`."""
    client = _get_client()
    try:
        data = await client.get_resource("NixFact Inkoopfactuur", name)
    except NixfactError as e:
        return _err(e)
    return _result(data)


# --------------------------------------------------------------------------
# Bank transacties (NixFact Bank Transactie)
# --------------------------------------------------------------------------


@mcp.tool()
async def list_bank_transacties(
    bank_koppeling: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    only_unmatched: bool = False,
    limit_pages: int | None = None,
) -> str:
    """List bank transactions (NixFact Bank Transactie)."""
    filters: list[list[Any]] = []
    if bank_koppeling:
        filters.append(["bank_koppeling", "=", bank_koppeling])
    if from_date:
        filters.append(["datum", ">=", from_date])
    if to_date:
        filters.append(["datum", "<=", to_date])
    if only_unmatched:
        filters.append(["status", "=", "Niet gematcht"])
    client = _get_client()
    try:
        if limit_pages == 1:
            items = await client.list_resource(
                "NixFact Bank Transactie",
                filters=filters or None,
                fields=["*"],
                limit_page_length=100,
                order_by="datum desc",
            )
        else:
            items = await client.list_resource_all(
                "NixFact Bank Transactie",
                filters=filters or None,
                fields=["*"],
                max_pages=limit_pages or 1000,
                order_by="datum desc",
            )
    except NixfactError as e:
        return _err(e)
    return _result(
        {"status": "success", "totalresults": len(items), "transacties": items}
    )


@mcp.tool()
async def sync_ponto(bank_koppeling_id: str) -> str:
    """Sync transactions from Ponto for a NixFact Bank Koppeling, then run
    matching. Wraps `nixfact_integration.api.bank.sync_ponto_transactions`.
    """
    client = _get_client()
    try:
        data = await client.call_method(
            "nixfact_integration.api.bank.sync_ponto_transactions",
            params={"bank_koppeling_id": bank_koppeling_id},
        )
    except NixfactError as e:
        return _err(e)
    return _result(data)


# --------------------------------------------------------------------------
# UBL e-invoicing
# --------------------------------------------------------------------------


@mcp.tool()
async def generate_ubl(factuur_name: str) -> str:
    """Generate UBL 2.1 XML for a NixFact Factuur and return it inline.

    Wraps `nixfact_integration.api.ubl.generate_ubl_xml`.
    """
    client = _get_client()
    try:
        data = await client.call_method(
            "nixfact_integration.api.ubl.generate_ubl_xml",
            params={"factuur_name": factuur_name},
        )
    except NixfactError as e:
        return _err(e)
    return _result(data)


@mcp.tool()
async def attach_ubl(factuur_name: str) -> str:
    """Generate UBL XML, attach it to the invoice, return the file URL.

    Wraps `nixfact_integration.api.ubl.attach_ubl_to_factuur`.
    """
    client = _get_client()
    try:
        data = await client.call_method(
            "nixfact_integration.api.ubl.attach_ubl_to_factuur",
            params={"factuur_name": factuur_name},
        )
    except NixfactError as e:
        return _err(e)
    return _result(data)


# --------------------------------------------------------------------------
# Mollie payment links
# --------------------------------------------------------------------------


@mcp.tool()
async def create_mollie_payment_link(factuur_name: str) -> str:
    """Create a Mollie payment link for a NixFact Factuur.

    Wraps `nixfact_integration.api.mollie.create_payment_link`.
    """
    client = _get_client()
    try:
        data = await client.call_method(
            "nixfact_integration.api.mollie.create_payment_link",
            params={"factuur_name": factuur_name},
        )
    except NixfactError as e:
        return _err(e)
    return _result(data)


# --------------------------------------------------------------------------
# Statistieken / dashboard
# --------------------------------------------------------------------------


@mcp.tool()
async def get_dashboard(
    periode: str = "maand",
    jaar: int | None = None,
    maand: int | None = None,
) -> str:
    """Fetch dashboard statistics for a period.

    Args:
        periode: "maand", "kwartaal", or "jaar".
        jaar: defaults to current year.
        maand: defaults to current month (only used when periode="maand").
    """
    params: dict[str, Any] = {"periode": periode}
    if jaar is not None:
        params["jaar"] = jaar
    if maand is not None:
        params["maand"] = maand
    client = _get_client()
    try:
        data = await client.call_method(
            "nixfact_integration.api.statistieken.get_dashboard_data",
            params=params,
            http_method="GET",
        )
    except NixfactError as e:
        return _err(e)
    return _result(data)


@mcp.tool()
async def get_btw_overzicht(kwartaal: int, jaar: int | None = None) -> str:
    """BTW overzicht per kwartaal."""
    params: dict[str, Any] = {"kwartaal": kwartaal}
    if jaar is not None:
        params["jaar"] = jaar
    client = _get_client()
    try:
        data = await client.call_method(
            "nixfact_integration.api.statistieken.get_btw_overzicht",
            params=params,
            http_method="GET",
        )
    except NixfactError as e:
        return _err(e)
    return _result(data)


@mcp.tool()
async def get_omzet_per_klant(jaar: int | None = None) -> str:
    """Revenue breakdown by customer for a given year."""
    params: dict[str, Any] = {}
    if jaar is not None:
        params["jaar"] = jaar
    client = _get_client()
    try:
        data = await client.call_method(
            "nixfact_integration.api.statistieken.get_omzet_per_klant",
            params=params,
            http_method="GET",
        )
    except NixfactError as e:
        return _err(e)
    return _result(data)


@mcp.tool()
async def get_kosten_per_categorie(jaar: int | None = None) -> str:
    """Cost breakdown by category for a given year."""
    params: dict[str, Any] = {}
    if jaar is not None:
        params["jaar"] = jaar
    client = _get_client()
    try:
        data = await client.call_method(
            "nixfact_integration.api.statistieken.get_kosten_per_categorie",
            params=params,
            http_method="GET",
        )
    except NixfactError as e:
        return _err(e)
    return _result(data)


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------


@mcp.tool()
async def whoami() -> str:
    """Sanity-check the API connection. Returns the logged-in Frappe user."""
    client = _get_client()
    try:
        data = await client.call_method(
            "frappe.auth.get_logged_user", http_method="GET"
        )
    except NixfactError as e:
        return _err(e)
    return _result({"base_url": client.base_url, "user": data})


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------


@mcp.prompt()
def import_from_wefact() -> str:
    """Walk through importing a WeFact administration into Nixfact."""
    return (
        "I want to import my WeFact administration into Nixfact (Frappe/ERPNext). "
        "Please:\n"
        "1. Use `whoami` to confirm the Nixfact connection works.\n"
        "2. Use `list_klanten`, `list_facturen`, `list_offertes`, "
        "`list_abonnementen`, `list_inkoopfacturen` (each with `limit_pages=1` "
        "first) to inspect the current Nixfact field shapes.\n"
        "3. For each WeFact resource (debtor, invoice, creditinvoice, "
        "subscription, product), produce a mapping table to its Nixfact "
        "DocType and field names.\n"
        "4. Generate a Python migration script that reads WeFact JSON "
        "exports and creates the Nixfact records via `nixfact_resource_create` "
        "or the dedicated `create_*` tools.\n"
        "5. Flag any WeFact features that do NOT have a Nixfact equivalent "
        "yet (reminder ladders, summation/collection, custom email templates).\n"
    )


@mcp.prompt()
def feature_audit() -> str:
    """Audit the Nixfact account to inventory which features are in use."""
    return (
        "Audit my Nixfact account to inventory which features are actually "
        "in use. Steps:\n"
        "1. Sample klanten, facturen, offertes, abonnementen, inkoopfacturen, "
        "bank transacties.\n"
        "2. Identify all distinct values of: status (per DocType), "
        "kostencategorie, btw_percentage, kanaal, factuur_template.\n"
        "3. Check which Mollie/Ponto integrations have active koppelingen.\n"
        "4. Pull `get_dashboard` for the current month and `get_btw_overzicht` "
        "for the current quarter to confirm reporting works end-to-end.\n"
        "5. Output a feature-coverage table comparing Nixfact-used-by-me vs "
        "WeFact-equivalent vs Nixfact-roadmap-gap.\n"
    )


def run() -> None:
    """Entrypoint: start the MCP server over stdio."""
    mcp.run()
