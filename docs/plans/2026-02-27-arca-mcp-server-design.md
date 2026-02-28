# ARCA MCP Server — Design Document

**Date:** 2026-02-27
**Status:** Approved, ready for implementation
**Author:** Juan / Claude

---

## Problem

The ARCA prototype exposes ~22 operations (AFIP comprobantes, retenciones, notificaciones, Colppy reconciliation, CUIT enrichment, Banco Galicia) through a FastAPI HTTP server + React frontend. This is good for visual use but requires the server to be running, forces every consumer to speak HTTP, and is not accessible from Claude Desktop or AI agent pipelines without additional integration work.

**Goal:** Expose all operations as MCP tools so they can be used conversationally in Claude Desktop and programmatically by AI agents — without replacing or breaking the existing FastAPI + React stack.

---

## Chosen Approach: Smart Tools with Cache-First Behavior (Approach B)

Selected over:
- **Approach A** (1:1 endpoint mapping) — too many tools (30+), leaks cache/live split to callers
- **Approach C** (MCP resources + tools) — correct semantically but harder to use conversationally

### Key design decisions

1. **MCP server calls the Python service layer directly** — no HTTP roundtrips. Imports `comprobantes_api.py`, `retenciones_api.py`, `arca_db.py`, etc. from the existing service layer.
2. **Shares the SQLite database** (`arca_notifications.db`) with the existing FastAPI server — data cached by the React frontend is instantly available to the MCP server and vice versa.
3. **14 tools** (down from 22 operations) — cache/live split is hidden inside each tool. Callers get a `force_refresh` parameter when they need control.
4. **Credentials from `.env`** — MCP server reads the same `.env` as FastAPI at startup. Single configured identity.
5. **Services initialized once at startup** — pandas RNS DataFrame (1.2M rows, ~12s load), SQLite connection, Colppy API client. Playwright-based scrapers initialized lazily on first use.
6. **Transport:** stdio (Claude Desktop default). SSE available for remote/agent use.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        MCP Clients                              │
│   Claude Desktop          Claude Code          AI Agents        │
└────────────────┬──────────────────┬───────────────┬────────────┘
                 │  MCP protocol    │               │
                 ▼                  ▼               ▼
┌─────────────────────────────────────────────────────────────────┐
│        arca-prototype/backend/mcp_server.py                     │
│               (FastMCP, 14 tools)                               │
│                                                                 │
│  Reads .env at startup:                                         │
│    ARCA_CUIT, ARCA_CLAVE_FISCAL,                                │
│    COLPPY_USER, COLPPY_PASSWORD,                                │
│    TUSFACTURAS_API_KEY, ...                                     │
└──────┬──────────────┬──────────────┬──────────────┬────────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
 comprobantes_  retenciones_  colppy_api.py  reconciliacion_
 api.py         api.py                       *.py
 notifications_ libro_iva_    arca_db.py     rns_name_
 api.py         converter.py  (SQLite cache) search.py
 banco_galicia_ wsaa_client.py               afip_cuit_
 scraper.py                                  lookup.py
       │
       ▼
  arca_notifications.db  (shared with FastAPI)
```

---

## Tool Inventory (14 tools)

### ARCA / AFIP (6 tools)

| Tool | Description |
|------|-------------|
| `get_comprobantes` | Get AFIP invoices (recibidos or emitidos) for a date range. Cache-first. |
| `get_retenciones` | Get retenciones/percepciones from ARCA Mirequa. Cache-first. |
| `get_notificaciones` | Get DFE notifications with full message content. Cache-first. Supports `cuit_representado` for accountants. |
| `get_representados` | List all CUITs this account can act on behalf of. |
| `generate_libro_iva` | Generate AFIP Libro IVA Digital ZIP from cached comprobantes. Returns file path. |
| `test_wsaa_auth` | Test WSAA X.509 certificate authentication. |

### Colppy ERP (2 tools)

| Tool | Description |
|------|-------------|
| `get_colppy_comprobantes` | Get Colppy invoices (venta or compra) for a company and date range. |
| `get_colppy_empresas` | List all companies accessible in Colppy. Returns `id_empresa` needed for other tools. |

### Reconciliation (3 tools)

| Tool | Description |
|------|-------------|
| `reconcile_arca_vs_colppy` | Cross-reference ARCA comprobantes vs Colppy invoices by CAE. Returns matched/mismatch/only_arca/only_colppy buckets. |
| `reconcile_retenciones` | Cross-reference ARCA retenciones vs comprobantes recibidos by agent CUIT and period. |
| `search_invoices` | Natural-language search over invoice/reconciliation data (GPT-4o-mini). |

### CUIT Enrichment (2 tools)

| Tool | Description |
|------|-------------|
| `enrich_cuit` | Live AFIP lookup (TusFacturas API) + RNS dataset lookup. Returns razon_social, condicion_iva, actividades, company age, tipo_societario, provincia, incorporation date. |
| `search_company_by_name` | Search 1.24M companies by name to find CUIT. Autocomplete-friendly. Province filter supported. |

### Banco Galicia (1 tool)

| Tool | Description |
|------|-------------|
| `get_bank_transactions` | Get account transactions with ingresos/egresos/neto summary. Scrapes live if cache empty or force_refresh=True. |

---

## Tool Signatures

```python
# ARCA
get_comprobantes(fecha_desde: str, fecha_hasta: str, direccion: str = "recibidos", force_refresh: bool = False) -> list[dict]
get_retenciones(fecha_desde: str, fecha_hasta: str, force_refresh: bool = False) -> list[dict]
get_notificaciones(force_refresh: bool = False, cuit_representado: str = None) -> list[dict]
get_representados() -> list[dict]
generate_libro_iva(fecha_desde: str, fecha_hasta: str, tipo: str = "ventas") -> str
test_wsaa_auth() -> dict

# Colppy
get_colppy_comprobantes(id_empresa: str, from_date: str, to_date: str, tipo: str = "venta") -> list[dict]
get_colppy_empresas() -> list[dict]

# Reconciliation
reconcile_arca_vs_colppy(id_empresa: str, fecha_desde: str, fecha_hasta: str, direccion: str = "emitidos") -> dict
reconcile_retenciones(fecha_desde: str, fecha_hasta: str) -> dict
search_invoices(query: str, scope: str = "discrepancies") -> str

# CUIT Enrichment
enrich_cuit(cuit: str) -> dict
search_company_by_name(query: str, provincia: str = None, limit: int = 10) -> list[dict]

# Banco
get_bank_transactions(fecha_desde: str = None, fecha_hasta: str = None, account: str = "CA$", force_refresh: bool = False) -> dict
```

---

## Cache-First Logic

Every tool that has a live-fetch variant follows this pattern:

```
Tool called
      │
      ▼
force_refresh=True?
      │
  No  │  Yes
      │   └─────────────────────────────┐
      ▼                                 ▼
Query SQLite cache            Call live ARCA service
      │                                 │
      ▼                                 ▼
Data found?                   Save to SQLite cache
      │                                 │
  Yes │  No ────────────────────────────┘
      │
      ▼
Return data + _meta: {source, cached_at, count, cuit}
```

Every response includes `_meta`:
```json
{
  "_meta": {
    "source": "cache",
    "cached_at": "2026-02-27T14:30:00",
    "count": 42,
    "cuit": "20-26844853-6"
  }
}
```

---

## Error Handling

| Error type | Behavior |
|---|---|
| Live API fails (ARCA down, Playwright timeout, wrong password) | Return cached data + `{_meta: {source: "cache_fallback", error: "..."}}`. If no cache, raise descriptive MCP error. |
| Cache miss + no credentials (no `.env`) | Raise MCP error: `"No cached data. Set ARCA_CUIT and ARCA_CLAVE_FISCAL in .env to fetch live."` |
| Live fetch returns 0 results | Return empty list with `_meta`. Never silently fail. |

---

## File Structure

```
arca-prototype/
├── backend/
│   ├── mcp_server.py          ← NEW (~400 lines, single file)
│   ├── main.py                (unchanged)
│   ├── routers/               (unchanged)
│   └── services/              (unchanged — MCP imports these)
├── .env                       (unchanged)
└── mcp_config.json            ← NEW: Claude Desktop registration
```

`mcp_config.json` (to add to Claude Desktop MCP settings):
```json
{
  "mcpServers": {
    "arca": {
      "command": "python",
      "args": ["/Users/virulana/openai-cookbook/arca-prototype/backend/mcp_server.py"],
      "env": {
        "PYTHONPATH": "/Users/virulana/openai-cookbook/arca-prototype/backend"
      }
    }
  }
}
```

---

## Dependencies

New dependency: `fastmcp` (or `mcp` SDK). Add to `requirements.txt`:
```
fastmcp>=0.9.0
```

All other dependencies are already present in the existing `requirements.txt`.

---

## Out of Scope

- PDF attachment download/serve via MCP (binary data, better served via FastAPI)
- Reconciliation acknowledgment write operations via MCP (use React frontend or direct DB)
- Multi-user / multi-CUIT credential management (single `.env` identity is sufficient for personal + agent use)
- SSE transport configuration (stdio is sufficient; SSE can be added post-MVP if needed for remote agents)
