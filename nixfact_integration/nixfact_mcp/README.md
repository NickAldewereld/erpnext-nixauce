# nixfact-mcp

An [MCP](https://modelcontextprotocol.io) server for [Nixfact](https://nixfact.eu),
the Frappe/ERPNext-based Dutch invoicing app. Lets any MCP-compatible client
(Claude Desktop, Claude Code, Cursor, Zed, …) read and modify a Nixfact
administration through the Frappe REST API.

This is the Nixfact-side counterpart of [`wefact-mcp`](../../../wefact-mcp/),
intentionally shaped the same way so the two can be used side-by-side during
a WeFact → Nixfact migration.

> **Status:** alpha. The generic `nixfact_method` and
> `nixfact_resource_*` tools already cover the entire Frappe API.
> Higher-level tools wrap the most common Nixfact operations.

## Quick start

### 1. Install

```bash
pip install -e .
```

### 2. Generate Frappe API credentials

In Nixfact / ERPNext: open your **User profile → API Access → Generate Keys**.
You'll get an `api_key` (visible) and `api_secret` (shown once — copy it).

### 3. Configure your MCP client

#### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "nixfact": {
      "command": "nixfact-mcp",
      "env": {
        "NIXFACT_BASE_URL": "https://erp.example.com",
        "NIXFACT_API_KEY": "your-api-key",
        "NIXFACT_API_SECRET": "your-api-secret"
      }
    }
  }
}
```

#### Claude Code

```bash
claude mcp add nixfact \
  -e NIXFACT_BASE_URL=https://erp.example.com \
  -e NIXFACT_API_KEY=your-api-key \
  -e NIXFACT_API_SECRET=your-api-secret \
  -- nixfact-mcp
```

Restart your client and the Nixfact tools should appear.

## Tools

### Generic escape hatches

| Tool | Purpose |
|---|---|
| `nixfact_method(method, params, http_method)` | Call any whitelisted Frappe method. |
| `nixfact_resource_list(doctype, filters, fields, order_by, limit_pages)` | List rows of any DocType. |
| `nixfact_resource_get(doctype, name)` | Fetch one document. |
| `nixfact_resource_create(doctype, fields)` | Create any DocType. |
| `nixfact_resource_update(doctype, name, fields)` | Update any DocType. |
| `whoami()` | Sanity-check the connection. |

### Klanten (Customer)

`list_klanten`, `get_klant`

### Facturen (NixFact Factuur — verkoopfacturen)

`list_facturen`, `get_factuur`, `create_factuur`, `update_factuur`

### Offertes (NixFact Offerte)

`list_offertes`, `get_offerte`, `create_offerte`, `update_offerte_status`
(the `*_offerte*` tools wrap the dedicated `nixfact_integration.api.*` helpers)

### Abonnementen (NixFact Abonnement)

`list_abonnementen`, `get_abonnement`

### Inkoopfacturen (NixFact Inkoopfactuur)

`list_inkoopfacturen`, `get_inkoopfactuur`

### Bank

`list_bank_transacties`, `sync_ponto`

### UBL e-invoicing

`generate_ubl`, `attach_ubl`

### Mollie

`create_mollie_payment_link`

### Statistieken

`get_dashboard`, `get_btw_overzicht`, `get_omzet_per_klant`,
`get_kosten_per_categorie`

### Prompts

| Prompt | Purpose |
|---|---|
| `import_from_wefact` | Walk through migrating a WeFact administration into Nixfact. |
| `feature_audit` | Inventory which Nixfact features the account uses. |

## Field names

Tools that take `fields` use the **Nixfact DocType field names verbatim**
(Dutch where Nixfact is Dutch: `factuur_datum`, `bedrag_excl_btw`,
`klant`, `vervaldatum`, …). The whitelisted helpers under
`nixfact_integration.api.*` keep their original argument names too.

## Pagination & filtering

List tools fetch all pages by default. Pass `limit_pages=1` to get only
the first page (fast for exploration). Pass `modified_since="2026-01-01"`
for incremental sync — this maps to a Frappe `["modified", ">=", date]`
filter.

The generic `nixfact_resource_list` accepts arbitrary Frappe filter
syntax, e.g.:

```
filters=[["status","=","Verstuurd"], ["factuur_datum",">=","2026-01-01"]]
fields=["name","factuurnummer","bedrag_incl_btw","status"]
order_by="factuur_datum desc"
```

## Example session

```
> Use the nixfact `whoami` tool.
{"base_url": "https://erp.example.com", "user": "nick@nixpay.nl"}

> List facturen with status Verstuurd, this year only.
[uses list_facturen status=Verstuurd from_date=2026-01-01]

> Generate UBL XML for FAC-2026-00007 and attach it.
[uses attach_ubl factuur_name=FAC-2026-00007]
```

## Sister project

If you also have a WeFact account, install [`wefact-mcp`](../../../wefact-mcp/)
in the same MCP client. With both servers running you can:

1. `wefact-mcp / list_debtors` → export
2. Map fields with the `import_from_wefact` prompt
3. `nixfact / nixfact_resource_create` → import

This is the workflow the `import_from_wefact` and
`wefact-mcp / export_to_nixfact` prompts are designed for.

## Limitations / things to know

- Frappe uses **per-user API keys**. The MCP runs as whichever user
  generated the key — its permissions are constrained by that user's
  Role Permissions in Nixfact.
- Frappe's list endpoints default to returning only `name`. Pass
  `fields=["*"]` (or an explicit list) when you want anything else.
- Frappe versions differ in how strictly they validate filters. The
  client logs the structured error message Frappe returns; if a
  generic `nixfact_resource_list` call fails, fall back to
  `nixfact_method` and call `frappe.client.get_list` directly.

## License

AGPL-3.0-or-later. For commercial licensing: nick@nixpay.nl.

## Disclaimer

This project is not affiliated with or endorsed by Frappe Technologies.
ERPNext and Frappe are trademarks of their respective owners.
