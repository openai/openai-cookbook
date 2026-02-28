# ARCA MCP Server — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a single-file MCP server (`mcp_server.py`) that exposes all ARCA/Colppy/Enrichment operations as 14 callable MCP tools for Claude Desktop and AI agents.

**Architecture:** FastMCP decorator-based server that imports the existing Python service layer directly (no HTTP). Shares the existing SQLite database with the FastAPI server. Reads credentials from the same `.env`. Tools are cache-first: check SQLite first, call live API only when cache is empty or `force_refresh=True`.

**Tech Stack:** `fastmcp>=0.9.0`, existing `arca-prototype/backend/services/*.py`, `tools/scripts/rns_name_search.py`, `tools/scripts/afip_cuit_lookup.py`, Python `asyncio`, `python-dotenv`

**Design doc:** `docs/plans/2026-02-27-arca-mcp-server-design.md`

---

## Context for the implementer

The codebase is at `arca-prototype/`. Before coding each task, read the relevant service file — the functions are already written, the MCP tools are thin wrappers around them.

**Critical env vars** (already in `.env`):
- `ARCA_CUIT` — 11-digit CUIT (no dashes)
- `ARCA_PASSWORD` — Clave Fiscal
- `COLPPY_AUTH_USER`, `COLPPY_AUTH_PASSWORD`, `COLPPY_USER`, `COLPPY_PASSWORD`
- `TUSFACTURAS_API_KEY`, `TUSFACTURAS_USER_TOKEN`, `TUSFACTURAS_API_TOKEN`

**The SQLite DB** is at `arca-prototype/data/arca_notifications.db`. All read functions are in `backend/services/arca_db.py` as module-level functions (not a class). Import them directly.

**Colppy pattern:** Every Colppy call must: `login()` → get `claveSesion` → call operation → `logout(clave)`. The session is short-lived; do not cache it.

**Playwright services** (comprobantes, retenciones, notificaciones, banco galicia) are async and launch a browser. They are slow (~10-30s) and should only be called when `force_refresh=True` or when the cache is empty.

---

## Task 1: Add FastMCP dependency

**Files:**
- Modify: `arca-prototype/requirements.txt`

**Step 1: Add fastmcp to requirements.txt**

Add this line to `arca-prototype/requirements.txt`:
```
fastmcp>=0.9.0
```

**Step 2: Install it**

```bash
cd arca-prototype
pip install fastmcp
```

Expected: `Successfully installed fastmcp-...`

**Step 3: Verify the import works**

```bash
python -c "from fastmcp import FastMCP; print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add arca-prototype/requirements.txt
git commit -m "feat(mcp): add fastmcp dependency"
```

---

## Task 2: Create mcp_server.py skeleton

**Files:**
- Create: `arca-prototype/backend/mcp_server.py`

**Step 1: Write the skeleton**

```python
#!/usr/bin/env python3
"""
ARCA MCP Server

Exposes all ARCA/AFIP/Colppy/Enrichment operations as MCP tools for use
in Claude Desktop and AI agent pipelines.

Calls the Python service layer directly (no HTTP). Shares SQLite cache with
the FastAPI server. Credentials are read from .env at startup.

Run:
    cd arca-prototype/backend
    python mcp_server.py

Claude Desktop config (add to ~/Library/Application Support/Claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "arca": {
          "command": "python",
          "args": ["/absolute/path/to/arca-prototype/backend/mcp_server.py"]
        }
      }
    }
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
# Ensure the backend/ directory is importable (for `from services.xxx import yyy`)
_backend_dir = Path(__file__).resolve().parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# Ensure tools/scripts/ is importable (for rns_name_search, afip_cuit_lookup)
_tools_scripts = _backend_dir.parent.parent / "tools" / "scripts"
if str(_tools_scripts) not in sys.path:
    sys.path.insert(0, str(_tools_scripts))

# ── Load .env ─────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
_env_path = _backend_dir.parent / ".env"
load_dotenv(_env_path)

# ── FastMCP server ────────────────────────────────────────────────────────────
from fastmcp import FastMCP
mcp = FastMCP(
    "arca",
    instructions=(
        "ARCA MCP Server: access AFIP/ARCA tax data, Colppy ERP invoices, "
        "reconciliation reports, CUIT enrichment, and Banco Galicia transactions. "
        "All tools read from SQLite cache by default and call live APIs only when "
        "force_refresh=True or when the cache is empty."
    ),
)

# ── Shared config ─────────────────────────────────────────────────────────────
_CUIT = "".join(c for c in os.getenv("ARCA_CUIT", "") if c.isdigit())
_PASSWORD = os.getenv("ARCA_PASSWORD", "")


def _meta(source: str, count: int = 0, **extra) -> dict:
    """Build a standard _meta block to attach to every tool response."""
    return {
        "_meta": {
            "source": source,
            "fetched_at": datetime.utcnow().isoformat(),
            "count": count,
            "cuit": _CUIT,
            **extra,
        }
    }


# ── Lazy-initialised heavy services ──────────────────────────────────────────
_rns_search = None


def _get_rns():
    """Load RNS search index on first use (~12s, then cached in process memory)."""
    global _rns_search
    if _rns_search is None:
        from rns_name_search import RNSNameSearch
        _rns_search = RNSNameSearch()
    return _rns_search


# ── Tool stubs (will be filled in Tasks 3–11) ─────────────────────────────────

@mcp.tool()
def ping() -> dict:
    """Health check. Returns server status and configured CUIT."""
    return {
        "status": "ok",
        "cuit_configured": bool(_CUIT),
        "cuit_preview": f"{_CUIT[:2]}...{_CUIT[-2:]}" if _CUIT else None,
        "env_path": str(_env_path),
        "env_exists": _env_path.exists(),
    }


if __name__ == "__main__":
    mcp.run()
```

**Step 2: Run it to confirm it starts**

```bash
cd arca-prototype/backend
python mcp_server.py
```

Expected: Server starts, prints something like `Starting MCP server "arca"...` — it will block waiting for stdin (that's normal for stdio transport). Hit Ctrl+C.

**Step 3: Verify the ping tool is registered**

```bash
python -c "
import sys; sys.path.insert(0, 'arca-prototype/backend')
from mcp_server import mcp
tools = [t.name for t in mcp._tool_manager.list_tools()]
print('Tools:', tools)
assert 'ping' in tools
print('OK')
"
```

Expected: `Tools: ['ping']` then `OK`

**Step 4: Commit**

```bash
git add arca-prototype/backend/mcp_server.py
git commit -m "feat(mcp): add mcp_server.py skeleton with ping tool"
```

---

## Task 3: Implement get_notificaciones

**Files:**
- Read first: `arca-prototype/backend/services/arca_db.py` (look for `get_notifications`)
- Read first: `arca-prototype/backend/services/notifications_api.py` (look for `get_notifications_with_content`)
- Modify: `arca-prototype/backend/mcp_server.py`

**Step 1: Write the test**

Create `arca-prototype/backend/tests/test_mcp_notificaciones.py`:

```python
"""Tests for get_notificaciones MCP tool."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def test_get_notificaciones_returns_cached_data():
    """When cache has data, returns it without calling ARCA."""
    fake_notifications = [
        {"id": 1, "organismo": "AFIP", "mensaje_preview": "Test", "fetched_at": "2026-02-27T12:00:00"}
    ]
    with patch("services.arca_db.get_notifications", return_value=(fake_notifications, "2026-02-27")):
        from mcp_server import mcp
        # Call the tool function directly (not via MCP protocol)
        import importlib
        import mcp_server as ms
        # Re-import to pick up patches
        result = None
        for tool in mcp._tool_manager.list_tools():
            if tool.name == "get_notificaciones":
                result = asyncio.run(tool.fn())
                break
        assert result is not None
        assert result["count"] == 1
        assert result["_meta"]["source"] == "cache"

import asyncio
```

**Step 2: Run the test — expect it to fail (tool not yet implemented)**

```bash
cd arca-prototype
pytest backend/tests/test_mcp_notificaciones.py -v 2>&1 | head -30
```

Expected: `FAILED` or `AttributeError` because `get_notificaciones` doesn't exist yet.

**Step 3: Implement the tool**

Add after the `ping` tool stub in `mcp_server.py` (before `if __name__ == "__main__":`):

```python
@mcp.tool()
async def get_notificaciones(
    force_refresh: bool = False,
    cuit_representado: str = None,
) -> dict:
    """
    Get DFE (Domicilio Fiscal Electrónico) notifications from ARCA.
    Returns notifications with full message content and attachment metadata.
    Uses SQLite cache unless force_refresh=True.

    Args:
        force_refresh: If True, fetch live from ARCA (requires Clave Fiscal in .env).
        cuit_representado: CUIT of a representado to fetch for (accountant accounts only).
                           Defaults to the configured ARCA_CUIT.
    """
    from services.arca_db import get_notifications
    from services.notifications_api import get_notifications_with_content

    target_cuit = "".join(c for c in (cuit_representado or _CUIT) if c.isdigit())

    if not force_refresh:
        cached, fetched_at = get_notifications(target_cuit)
        if cached:
            return {
                "notifications": cached,
                "count": len(cached),
                **_meta("cache", len(cached), fetched_at=fetched_at),
            }

    # Cache miss or force_refresh — call live ARCA
    if not _CUIT or not _PASSWORD:
        return {
            "error": "No cached data. Set ARCA_CUIT and ARCA_PASSWORD in .env to fetch live.",
            "notifications": [],
            **_meta("error", 0),
        }

    try:
        result = await get_notifications_with_content(_CUIT, _PASSWORD, cuit_representado=target_cuit)
        notifications = result.get("notifications", [])
        return {
            "notifications": notifications,
            "count": len(notifications),
            **_meta("live", len(notifications)),
        }
    except Exception as e:
        # Fallback to cache on error
        cached, fetched_at = get_notifications(target_cuit)
        if cached:
            return {
                "notifications": cached,
                "count": len(cached),
                **_meta("cache_fallback", len(cached), error=str(e)),
            }
        return {
            "error": str(e),
            "notifications": [],
            **_meta("error", 0),
        }
```

**Step 4: Run the test — expect pass**

```bash
cd arca-prototype
pytest backend/tests/test_mcp_notificaciones.py -v
```

Expected: `PASSED`

**Step 5: Commit**

```bash
git add arca-prototype/backend/mcp_server.py arca-prototype/backend/tests/test_mcp_notificaciones.py
git commit -m "feat(mcp): add get_notificaciones tool"
```

---

## Task 4: Implement get_comprobantes

**Files:**
- Read first: `arca-prototype/backend/services/arca_db.py` (look for `get_comprobantes`, `get_last_fetched`)
- Read first: `arca-prototype/backend/services/comprobantes_api.py` (look for `get_comprobantes_recibidos`, `get_comprobantes_emitidos`)
- Modify: `arca-prototype/backend/mcp_server.py`

**Step 1: Write the test**

Create `arca-prototype/backend/tests/test_mcp_comprobantes.py`:

```python
"""Tests for get_comprobantes MCP tool."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _call_tool(name, **kwargs):
    import mcp_server as ms
    from importlib import reload
    for tool in ms.mcp._tool_manager.list_tools():
        if tool.name == name:
            return asyncio.run(tool.fn(**kwargs))
    raise AssertionError(f"Tool {name!r} not found")


def test_get_comprobantes_cached():
    """Returns cached data without calling ARCA when cache is populated."""
    fake_rows = [{"tipo_comp_nombre": "Factura A", "monto_total": "1000"}]
    with patch("services.arca_db.get_comprobantes", return_value=fake_rows):
        result = _call_tool(
            "get_comprobantes",
            fecha_desde="2026-01-01",
            fecha_hasta="2026-01-31",
            direccion="recibidos",
        )
    assert result["count"] == 1
    assert result["_meta"]["source"] == "cache"


def test_get_comprobantes_empty_cache_no_credentials():
    """Returns helpful error when cache is empty and no credentials configured."""
    import mcp_server as ms
    original_cuit = ms._CUIT
    original_pass = ms._PASSWORD
    ms._CUIT = ""
    ms._PASSWORD = ""
    try:
        with patch("services.arca_db.get_comprobantes", return_value=[]):
            result = _call_tool(
                "get_comprobantes",
                fecha_desde="2026-01-01",
                fecha_hasta="2026-01-31",
            )
        assert "error" in result
        assert result["count"] == 0
    finally:
        ms._CUIT = original_cuit
        ms._PASSWORD = original_pass
```

**Step 2: Run to confirm failure**

```bash
pytest arca-prototype/backend/tests/test_mcp_comprobantes.py -v 2>&1 | head -20
```

Expected: `FAILED` — tool not yet added.

**Step 3: Implement the tool**

Add to `mcp_server.py`:

```python
@mcp.tool()
async def get_comprobantes(
    fecha_desde: str,
    fecha_hasta: str,
    direccion: str = "recibidos",
    force_refresh: bool = False,
) -> dict:
    """
    Get AFIP invoices (comprobantes) for a date range.
    direccion must be "recibidos" (purchase invoices) or "emitidos" (sales invoices).
    Returns from SQLite cache unless force_refresh=True or cache is empty.

    Each comprobante includes: tipo_comp_nombre, punto_venta, numero_desde, cuit_emisor,
    denominacion, fecha_cbte, monto_total, neto_gravado, iva_total, cae, and more.
    """
    from services.arca_db import get_comprobantes as db_get
    from services.comprobantes_api import get_comprobantes_recibidos, get_comprobantes_emitidos

    if direccion not in ("recibidos", "emitidos"):
        return {"error": "direccion must be 'recibidos' or 'emitidos'", "comprobantes": [], **_meta("error", 0)}

    if not force_refresh:
        cached = db_get(_CUIT, direccion, fecha_desde, fecha_hasta)
        if cached:
            return {"comprobantes": cached, "count": len(cached), **_meta("cache", len(cached))}

    if not _CUIT or not _PASSWORD:
        return {
            "error": "No cached data. Set ARCA_CUIT and ARCA_PASSWORD in .env to fetch live.",
            "comprobantes": [],
            **_meta("error", 0),
        }

    try:
        fetch_fn = get_comprobantes_recibidos if direccion == "recibidos" else get_comprobantes_emitidos
        result = await fetch_fn(_CUIT, _PASSWORD, fecha_desde, fecha_hasta)
        comprobantes = result.get("comprobantes", [])
        return {"comprobantes": comprobantes, "count": len(comprobantes), **_meta("live", len(comprobantes))}
    except Exception as e:
        cached = db_get(_CUIT, direccion, fecha_desde, fecha_hasta)
        if cached:
            return {"comprobantes": cached, "count": len(cached), **_meta("cache_fallback", len(cached), error=str(e))}
        return {"error": str(e), "comprobantes": [], **_meta("error", 0)}
```

**Step 4: Run tests**

```bash
pytest arca-prototype/backend/tests/test_mcp_comprobantes.py -v
```

Expected: Both tests `PASSED`.

**Step 5: Commit**

```bash
git add arca-prototype/backend/mcp_server.py arca-prototype/backend/tests/test_mcp_comprobantes.py
git commit -m "feat(mcp): add get_comprobantes tool"
```

---

## Task 5: Implement get_retenciones

**Files:**
- Read first: `arca-prototype/backend/services/arca_db.py` (look for `get_retenciones`)
- Read first: `arca-prototype/backend/services/retenciones_api.py` (look for `download_retenciones`)
- Modify: `arca-prototype/backend/mcp_server.py`

**Step 1: Add the tool** (same cache-first pattern as get_comprobantes)

```python
@mcp.tool()
async def get_retenciones(
    fecha_desde: str,
    fecha_hasta: str,
    force_refresh: bool = False,
) -> dict:
    """
    Get retenciones and percepciones from ARCA Mirequa for a date range.
    Includes SICORE, IVA, Ganancias retenciones grouped by agente and period.
    Returns from SQLite cache unless force_refresh=True or cache is empty.

    Each retencion includes: fecha, tipo_regimen, denominacion_agente, cuit_agente,
    numero_certificado, importe_retencion, impuesto.
    """
    from services.arca_db import get_retenciones as db_get
    from services.retenciones_api import download_retenciones

    if not force_refresh:
        cached = db_get(_CUIT, fecha_desde, fecha_hasta)
        if cached:
            return {"retenciones": cached, "count": len(cached), **_meta("cache", len(cached))}

    if not _CUIT or not _PASSWORD:
        return {
            "error": "No cached data. Set ARCA_CUIT and ARCA_PASSWORD in .env to fetch live.",
            "retenciones": [],
            **_meta("error", 0),
        }

    try:
        result = await download_retenciones(_CUIT, _PASSWORD, fecha_desde, fecha_hasta)
        retenciones = result.get("retenciones", [])
        return {"retenciones": retenciones, "count": len(retenciones), **_meta("live", len(retenciones))}
    except Exception as e:
        cached = db_get(_CUIT, fecha_desde, fecha_hasta)
        if cached:
            return {"retenciones": cached, "count": len(cached), **_meta("cache_fallback", len(cached), error=str(e))}
        return {"error": str(e), "retenciones": [], **_meta("error", 0)}
```

**Step 2: Write a smoke test and run**

```bash
python -c "
import sys; sys.path.insert(0, 'arca-prototype/backend')
from mcp_server import mcp
tools = [t.name for t in mcp._tool_manager.list_tools()]
assert 'get_retenciones' in tools, 'Tool missing!'
print('get_retenciones registered OK')
"
```

**Step 3: Commit**

```bash
git add arca-prototype/backend/mcp_server.py
git commit -m "feat(mcp): add get_retenciones tool"
```

---

## Task 6: Implement get_representados and test_wsaa_auth

**Files:**
- Read first: `arca-prototype/backend/services/arca_db.py` (look for `get_representados`)
- Read first: `arca-prototype/backend/services/notifications_api.py` (look for `get_representados`)
- Read first: `arca-prototype/backend/services/wsaa_client.py` (look for `get_credentials`)
- Modify: `arca-prototype/backend/mcp_server.py`

**Step 1: Add both tools**

```python
@mcp.tool()
async def get_representados(force_refresh: bool = False) -> dict:
    """
    List all CUITs this ARCA account can act on behalf of (representados).
    Accountant accounts typically have multiple representados (their clients).
    Returns from SQLite cache unless force_refresh=True.

    Each representado includes: cuit_representado, nombre, fetched_at.
    """
    from services.arca_db import get_representados as db_get
    from services.notifications_api import get_representados as api_get

    if not force_refresh:
        cached = db_get(_CUIT)
        if cached:
            return {"representados": cached, "count": len(cached), **_meta("cache", len(cached))}

    if not _CUIT or not _PASSWORD:
        return {
            "error": "No cached data. Set ARCA_CUIT and ARCA_PASSWORD in .env.",
            "representados": [],
            **_meta("error", 0),
        }

    try:
        result = await api_get(_CUIT, _PASSWORD)
        representados = result.get("representados", [])
        return {"representados": representados, "count": len(representados), **_meta("live", len(representados))}
    except Exception as e:
        return {"error": str(e), "representados": [], **_meta("error", 0)}


@mcp.tool()
def test_wsaa_auth() -> dict:
    """
    Test WSAA X.509 certificate authentication with AFIP.
    Returns success status and a preview of the obtained token.
    Requires ARCA_CERT_PATH and ARCA_KEY_PATH to be configured in .env.
    Useful to verify that certificate-based services (like factura electronica) are working.
    """
    from services.wsaa_client import get_credentials
    try:
        creds = get_credentials(service="veconsumerws")
        token = creds.get("token", "")
        return {
            "success": True,
            "token_preview": token[:20] + "..." if token else None,
            **_meta("live", 1),
        }
    except Exception as e:
        return {"success": False, "error": str(e), **_meta("error", 0)}
```

**Step 2: Verify tools are registered**

```bash
python -c "
import sys; sys.path.insert(0, 'arca-prototype/backend')
from mcp_server import mcp
names = [t.name for t in mcp._tool_manager.list_tools()]
assert 'get_representados' in names
assert 'test_wsaa_auth' in names
print('Tools registered:', names)
"
```

**Step 3: Commit**

```bash
git add arca-prototype/backend/mcp_server.py
git commit -m "feat(mcp): add get_representados and test_wsaa_auth tools"
```

---

## Task 7: Implement generate_libro_iva

**Files:**
- Read first: `arca-prototype/backend/services/libro_iva_converter.py` (look for `build_libro_iva_zip`, `comprobantes_to_libro_iva`)
- Read first: `arca-prototype/backend/routers/arca.py` — the `/libro-iva/generate` endpoint shows the exact call pattern
- Modify: `arca-prototype/backend/mcp_server.py`

**Step 1: Add the tool**

```python
@mcp.tool()
def generate_libro_iva(
    fecha_desde: str,
    fecha_hasta: str,
    tipo: str = "ventas",
) -> dict:
    """
    Generate the AFIP Libro IVA Digital ZIP file from cached comprobantes.
    tipo must be "ventas" or "compras".

    IMPORTANT: Run get_comprobantes first to populate the cache for the date range.
    The ZIP file is saved to arca-prototype/data/ and the path is returned.

    The generated ZIP contains fixed-position-format files as required by AFIP:
    - Cabecera records (266 chars each)
    - Alicuotas records (ventas: 62 chars, compras: 84 chars)
    """
    from services.arca_db import get_comprobantes as db_get
    from services.libro_iva_converter import build_libro_iva_zip

    if tipo not in ("ventas", "compras"):
        return {"error": "tipo must be 'ventas' or 'compras'"}

    direccion = "emitidos" if tipo == "ventas" else "recibidos"
    comprobantes = db_get(_CUIT, direccion, fecha_desde, fecha_hasta)

    if not comprobantes:
        return {
            "error": (
                f"No cached comprobantes for {tipo} {fecha_desde} to {fecha_hasta}. "
                f"Run get_comprobantes(fecha_desde='{fecha_desde}', fecha_hasta='{fecha_hasta}', "
                f"direccion='{direccion}') first."
            )
        }

    try:
        zip_path = build_libro_iva_zip(comprobantes, tipo, _CUIT, fecha_desde, fecha_hasta)
        return {
            "success": True,
            "zip_path": str(zip_path),
            "comprobantes_count": len(comprobantes),
            "tipo": tipo,
            "periodo": f"{fecha_desde} to {fecha_hasta}",
        }
    except Exception as e:
        return {"error": str(e)}
```

**Step 2: Check the actual signature of `build_libro_iva_zip`**

Read `arca-prototype/backend/services/libro_iva_converter.py` and adjust the call above to match the actual function signature if it differs.

**Step 3: Smoke test**

```bash
python -c "
import sys; sys.path.insert(0, 'arca-prototype/backend')
from mcp_server import mcp
names = [t.name for t in mcp._tool_manager.list_tools()]
assert 'generate_libro_iva' in names
print('OK')
"
```

**Step 4: Commit**

```bash
git add arca-prototype/backend/mcp_server.py
git commit -m "feat(mcp): add generate_libro_iva tool"
```

---

## Task 8: Implement Colppy tools

**Files:**
- Read first: `arca-prototype/backend/services/colppy_api.py` — key functions: `login()`, `logout(clave)`, `list_empresas(clave)`, `list_facturas_venta(clave, id_empresa, from_date, to_date)`, `list_facturas_compra(clave, id_empresa, from_date, to_date)`
- Read first: `arca-prototype/backend/routers/colppy.py` to see the exact call pattern
- Modify: `arca-prototype/backend/mcp_server.py`

**Step 1: Write the test**

Create `arca-prototype/backend/tests/test_mcp_colppy.py`:

```python
"""Tests for Colppy MCP tools."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _call_tool(name, **kwargs):
    import mcp_server as ms
    for tool in ms.mcp._tool_manager.list_tools():
        if tool.name == name:
            return asyncio.run(tool.fn(**kwargs))
    raise AssertionError(f"Tool {name!r} not found")


def test_get_colppy_empresas_success():
    """Returns empresa list on successful Colppy login."""
    mock_login = AsyncMock(return_value={"success": True, "data": {"claveSesion": "abc123"}})
    mock_empresas = AsyncMock(return_value={"success": True, "data": [
        {"IdEmpresa": "1", "Nombre": "Test SRL", "CUIT": "30123456789"}
    ]})
    mock_logout = AsyncMock(return_value=None)

    with patch("services.colppy_api.login", mock_login), \
         patch("services.colppy_api.list_empresas", mock_empresas), \
         patch("services.colppy_api.logout", mock_logout):
        result = _call_tool("get_colppy_empresas")

    assert result["count"] == 1
    assert result["empresas"][0]["nombre"] == "Test SRL"
```

**Step 2: Run to confirm failure**

```bash
pytest arca-prototype/backend/tests/test_mcp_colppy.py -v 2>&1 | head -20
```

**Step 3: Add Colppy tools**

```python
@mcp.tool()
async def get_colppy_empresas() -> dict:
    """
    List all companies accessible in Colppy.
    Returns id_empresa, nombre, razon_social, cuit, and activa for each company.
    The id_empresa value is required by get_colppy_comprobantes.
    """
    from services import colppy_api

    login_result = await colppy_api.login()
    if not login_result["success"]:
        return {"error": f"Colppy login failed: {login_result['message']}", "empresas": [], "count": 0}

    clave = login_result["data"]["claveSesion"]
    try:
        result = await colppy_api.list_empresas(clave)
        if not result["success"]:
            return {"error": result["message"], "empresas": [], "count": 0}

        empresas = [
            {
                "id_empresa": e.get("IdEmpresa"),
                "nombre": e.get("Nombre"),
                "razon_social": e.get("razonSocial"),
                "cuit": e.get("CUIT"),
                "activa": e.get("activa"),
            }
            for e in (result.get("data") or [])
        ]
        return {"empresas": empresas, "count": len(empresas)}
    finally:
        await colppy_api.logout(clave)


@mcp.tool()
async def get_colppy_comprobantes(
    id_empresa: str,
    from_date: str,
    to_date: str,
    tipo: str = "venta",
) -> dict:
    """
    Get Colppy invoices for a company and date range.
    tipo must be "venta" (facturas de venta / sales) or "compra" (facturas de compra / purchases).
    id_empresa can be found using get_colppy_empresas.
    Dates format: YYYY-MM-DD.

    Each comprobante includes: nroComprobante, fechaFactura, razonSocial, cuit,
    importeTotal, cae, and related fields.
    """
    from services import colppy_api

    if tipo not in ("venta", "compra"):
        return {"error": "tipo must be 'venta' or 'compra'", "comprobantes": [], "count": 0}

    login_result = await colppy_api.login()
    if not login_result["success"]:
        return {"error": f"Colppy login failed: {login_result['message']}", "comprobantes": [], "count": 0}

    clave = login_result["data"]["claveSesion"]
    try:
        if tipo == "venta":
            result = await colppy_api.list_facturas_venta(clave, id_empresa, from_date, to_date)
        else:
            result = await colppy_api.list_facturas_compra(clave, id_empresa, from_date, to_date)

        if not result["success"]:
            return {"error": result["message"], "comprobantes": [], "count": 0}

        comprobantes = result.get("data") or []
        return {"comprobantes": comprobantes, "count": len(comprobantes), "tipo": tipo}
    finally:
        await colppy_api.logout(clave)
```

> **Note:** The exact function names in `colppy_api.py` may differ — check the file. Look for functions like `list_facturas_venta`, `list_comprobantes_venta`, or `get_facturas`. Adjust the calls above to match.

**Step 4: Run tests**

```bash
pytest arca-prototype/backend/tests/test_mcp_colppy.py -v
```

Expected: `PASSED`

**Step 5: Commit**

```bash
git add arca-prototype/backend/mcp_server.py arca-prototype/backend/tests/test_mcp_colppy.py
git commit -m "feat(mcp): add get_colppy_empresas and get_colppy_comprobantes tools"
```

---

## Task 9: Implement reconciliation tools

**Files:**
- Read first: `arca-prototype/backend/services/reconciliacion_emitidos.py` — look for the main reconcile function
- Read first: `arca-prototype/backend/services/reconciliacion_service.py` — look for `reconcile_retenciones`
- Read first: `arca-prototype/backend/services/reconciliation_search.py` — look for the search function
- Read first: `arca-prototype/backend/routers/arca.py` — the `/reconcile/emitidos` and `/reconcile/emitidos/stream` endpoints show the call pattern
- Modify: `arca-prototype/backend/mcp_server.py`

**Step 1: Add the three reconciliation tools**

```python
@mcp.tool()
async def reconcile_arca_vs_colppy(
    id_empresa: str,
    fecha_desde: str,
    fecha_hasta: str,
    direccion: str = "emitidos",
) -> dict:
    """
    Cross-reference ARCA comprobantes vs Colppy invoices by CAE number.
    direccion must be "emitidos" (ARCA emitidos vs Colppy ventas) or
    "recibidos" (ARCA recibidos vs Colppy compras).

    IMPORTANT: Run get_comprobantes and get_colppy_comprobantes first to ensure
    the cache is populated for the date range.

    Returns buckets:
    - matched: same CAE found in both ARCA and Colppy with matching amounts
    - amount_mismatch: same CAE but different totals
    - only_arca: invoices in ARCA not found in Colppy
    - only_colppy: invoices in Colppy not found in ARCA
    - duplicate_cae: CAE appearing more than once
    """
    from services.arca_db import get_comprobantes as db_get_comp
    from services import colppy_api

    if direccion not in ("emitidos", "recibidos"):
        return {"error": "direccion must be 'emitidos' or 'recibidos'"}

    # Get ARCA data from cache
    arca_comprobantes = db_get_comp(_CUIT, direccion, fecha_desde, fecha_hasta)
    if not arca_comprobantes:
        return {
            "error": (
                f"No ARCA {direccion} cached for {fecha_desde}–{fecha_hasta}. "
                f"Run get_comprobantes(direccion='{direccion}') first."
            )
        }

    # Get Colppy data
    tipo_colppy = "venta" if direccion == "emitidos" else "compra"
    login_result = await colppy_api.login()
    if not login_result["success"]:
        return {"error": f"Colppy login failed: {login_result['message']}"}

    clave = login_result["data"]["claveSesion"]
    try:
        if tipo_colppy == "venta":
            colppy_result = await colppy_api.list_facturas_venta(clave, id_empresa, fecha_desde, fecha_hasta)
        else:
            colppy_result = await colppy_api.list_facturas_compra(clave, id_empresa, fecha_desde, fecha_hasta)
    finally:
        await colppy_api.logout(clave)

    if not colppy_result["success"]:
        return {"error": f"Colppy fetch failed: {colppy_result['message']}"}

    colppy_comprobantes = colppy_result.get("data") or []

    # Run reconciliation — import the service and call it directly
    # Check reconciliacion_emitidos.py or reconciliacion_recibidos.py for the function signature
    if direccion == "emitidos":
        from services.reconciliacion_emitidos import reconcile_emitidos
        result = reconcile_emitidos(arca_comprobantes, colppy_comprobantes)
    else:
        from services.reconciliacion_recibidos import reconcile_recibidos
        result = reconcile_recibidos(arca_comprobantes, colppy_comprobantes)

    return {
        **result,
        "arca_count": len(arca_comprobantes),
        "colppy_count": len(colppy_comprobantes),
        "periodo": f"{fecha_desde} to {fecha_hasta}",
    }


@mcp.tool()
def reconcile_retenciones_vs_comprobantes(
    fecha_desde: str,
    fecha_hasta: str,
) -> dict:
    """
    Cross-reference ARCA retenciones vs comprobantes recibidos for a period.
    Matches retenciones (withholding certificates) to their source invoices
    by agent CUIT and period.

    IMPORTANT: Run get_retenciones and get_comprobantes(direccion='recibidos') first.

    Returns matched pairs, orphan retenciones (no matching invoice), and periods
    with no comprobante data.
    """
    from services.arca_db import get_retenciones as db_get_ret, get_comprobantes as db_get_comp
    from services.reconciliacion_service import reconcile_retenciones as _reconcile

    retenciones = db_get_ret(_CUIT, fecha_desde, fecha_hasta)
    comprobantes = db_get_comp(_CUIT, "recibidos", fecha_desde, fecha_hasta)

    if not retenciones:
        return {"error": f"No cached retenciones for {fecha_desde}–{fecha_hasta}. Run get_retenciones first."}
    if not comprobantes:
        return {"error": f"No cached comprobantes recibidos for {fecha_desde}–{fecha_hasta}. Run get_comprobantes(direccion='recibidos') first."}

    try:
        result = _reconcile(retenciones, comprobantes)
        return result
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def search_invoices(
    query: str,
    scope: str = "discrepancies",
) -> str:
    """
    Natural-language search over ARCA/Colppy invoice and reconciliation data using AI.
    scope must be "discrepancies" (search only mismatches) or "all" (search all cached invoices).

    Example queries:
    - "facturas de más de $500k sin match en Colppy de enero"
    - "retenciones de AFIP del mes pasado"
    - "comprobantes emitidos a CUIT 30-12345678-9"
    - "qué facturas tienen diferencia de monto?"

    Returns a natural language answer with supporting invoice references.
    """
    from services.reconciliation_search import search as _search

    try:
        result = await _search(query, scope=scope, cuit=_CUIT)
        # search() may return a string (streamed answer) or dict — handle both
        if isinstance(result, dict):
            return result.get("answer", str(result))
        return result
    except Exception as e:
        return f"Search error: {e}"
```

> **Note:** The exact function names in `reconciliacion_emitidos.py` and `reconciliacion_recibidos.py` may differ from `reconcile_emitidos` / `reconcile_recibidos`. Read those files and adjust the import names above.

**Step 2: Smoke test**

```bash
python -c "
import sys; sys.path.insert(0, 'arca-prototype/backend')
from mcp_server import mcp
names = [t.name for t in mcp._tool_manager.list_tools()]
for name in ['reconcile_arca_vs_colppy', 'reconcile_retenciones_vs_comprobantes', 'search_invoices']:
    assert name in names, f'{name} missing'
print('All reconciliation tools registered:', names)
"
```

**Step 3: Commit**

```bash
git add arca-prototype/backend/mcp_server.py
git commit -m "feat(mcp): add reconcile_arca_vs_colppy, reconcile_retenciones, search_invoices tools"
```

---

## Task 10: Implement CUIT enrichment tools

**Files:**
- Read first: `tools/scripts/afip_cuit_lookup.py` — look for the main lookup function/class
- Read first: `tools/scripts/rns_name_search.py` — `RNSNameSearch.search()` and `RNSNameSearch.autocomplete()`
- Read first: `tools/scripts/rns_dataset_lookup.py` — `RNSDatasetLookup.lookup_cuit()`
- Modify: `arca-prototype/backend/mcp_server.py`

**Step 1: Write the test**

Create `arca-prototype/backend/tests/test_mcp_enrichment.py`:

```python
"""Tests for CUIT enrichment MCP tools."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_search_company_by_name_returns_results():
    """Returns ranked company matches from RNS dataset."""
    from dataclasses import dataclass

    @dataclass
    class FakeMatch:
        cuit: str = "30123456789"
        razon_social: str = "PANADERIA DON JOSE SRL"
        tipo_societario: str = "SRL"
        provincia: str = "Buenos Aires"
        actividad: str = "Elaboración de pan"
        fecha_contrato: str = "2018-01-01"
        score: float = 95.0

    mock_rns = MagicMock()
    mock_rns.search.return_value = [FakeMatch()]

    import mcp_server as ms
    ms._rns_search = mock_rns  # inject mock directly

    import asyncio
    for tool in ms.mcp._tool_manager.list_tools():
        if tool.name == "search_company_by_name":
            result = asyncio.run(tool.fn(query="panaderia don jose"))
            break

    assert result["count"] == 1
    assert result["companies"][0]["cuit"] == "30123456789"
    assert result["companies"][0]["razon_social"] == "PANADERIA DON JOSE SRL"
```

**Step 2: Run to confirm failure**

```bash
pytest arca-prototype/backend/tests/test_mcp_enrichment.py -v 2>&1 | head -20
```

**Step 3: Add enrichment tools**

```python
@mcp.tool()
async def enrich_cuit(cuit: str) -> dict:
    """
    Enrich a CUIT with data from AFIP (live) and the RNS national company registry.
    No Clave Fiscal required — uses TusFacturas.app public AFIP API.

    Returns:
    - razon_social, condicion_iva, estado (AFIP)
    - actividades with start period (AFIP)
    - fecha_contrato_social (company incorporation date from RNS)
    - tipo_societario (SA, SRL, SAS, etc. from RNS)
    - provincia, localidad (from RNS)
    - business_age_years (computed from fecha_contrato_social)

    Use this to enrich leads at signup without requiring Clave Fiscal.
    """
    import asyncio as _asyncio
    from datetime import date

    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {"error": "CUIT debe tener 11 dígitos (sin guiones)", "cuit": cuit}

    result: dict = {"cuit": cuit_clean}

    # 1. AFIP lookup via TusFacturas.app
    try:
        from afip_cuit_lookup import lookup_cuit_afip  # check actual function name in afip_cuit_lookup.py
        afip_data = await _asyncio.to_thread(lookup_cuit_afip, cuit_clean)
        result.update({
            "razon_social": afip_data.get("razon_social"),
            "condicion_iva": afip_data.get("condicion_impositiva"),
            "estado": afip_data.get("estado"),
            "actividades": afip_data.get("actividades", []),
            "domicilio": afip_data.get("direccion"),
            "provincia_afip": afip_data.get("provincia"),
        })
    except Exception as e:
        result["afip_error"] = str(e)

    # 2. RNS dataset lookup (local, fast)
    try:
        import sys as _sys
        _sys.path.insert(0, str(_tools_scripts))
        from rns_dataset_lookup import RNSDatasetLookup
        rns = RNSDatasetLookup()
        rns_result = rns.lookup_cuit(cuit_clean)
        if rns_result and rns_result.found:
            result.update({
                "fecha_contrato_social": rns_result.creation_date,
                "tipo_societario": rns_result.tipo_societario,
                "provincia_rns": rns_result.provincia,
                "actividad_rns": rns_result.actividad_descripcion,
            })
            # Compute business age
            if rns_result.creation_date:
                try:
                    from datetime import date, datetime
                    created = datetime.strptime(rns_result.creation_date[:10], "%Y-%m-%d").date()
                    result["business_age_years"] = round((date.today() - created).days / 365.25, 1)
                except Exception:
                    pass
    except Exception as e:
        result["rns_error"] = str(e)

    return result


@mcp.tool()
def search_company_by_name(
    query: str,
    provincia: str = None,
    limit: int = 10,
) -> dict:
    """
    Search 1.24 million Argentine companies by name to find their CUIT.
    Supports partial names (autocomplete-friendly). Province filter helps narrow results.

    Use this when a user doesn't know their CUIT and wants to search by company name.
    After finding the company, pass the CUIT to enrich_cuit for full details.

    Args:
        query: Company name or partial name (e.g. "panaderia martinez", "BANCO BBVA")
        provincia: Province to filter by (e.g. "Buenos Aires", "Córdoba", "Santa Fe")
        limit: Max number of results to return (default 10)

    Returns ranked matches with cuit, razon_social, tipo_societario, provincia, actividad.
    First load takes ~12s (loading 1.2M rows); subsequent calls are fast.
    """
    try:
        rns = _get_rns()
        matches = rns.search(query, provincia=provincia, limit=limit)
        companies = [
            {
                "cuit": m.cuit,
                "razon_social": m.razon_social,
                "tipo_societario": m.tipo_societario,
                "provincia": m.provincia,
                "actividad": m.actividad,
                "fecha_contrato": m.fecha_contrato,
                "score": m.score,
            }
            for m in matches
        ]
        return {"companies": companies, "count": len(companies), "query": query}
    except Exception as e:
        return {"error": str(e), "companies": [], "count": 0}
```

> **Note:** Check `tools/scripts/afip_cuit_lookup.py` for the actual function name and whether it's sync or async. It likely uses the TusFacturas.app REST API. If it's sync, wrap it with `asyncio.to_thread()` as shown above.

**Step 4: Run the test**

```bash
pytest arca-prototype/backend/tests/test_mcp_enrichment.py -v
```

Expected: `PASSED`

**Step 5: Commit**

```bash
git add arca-prototype/backend/mcp_server.py arca-prototype/backend/tests/test_mcp_enrichment.py
git commit -m "feat(mcp): add enrich_cuit and search_company_by_name tools"
```

---

## Task 11: Implement get_bank_transactions

**Files:**
- Read first: `arca-prototype/backend/services/arca_db.py` (look for `get_banco_transactions`)
- Read first: `arca-prototype/backend/services/banco_galicia_scraper.py` (look for `get_savings_account_statements`)
- Modify: `arca-prototype/backend/mcp_server.py`

**Step 1: Add the tool**

```python
@mcp.tool()
async def get_bank_transactions(
    fecha_desde: str = None,
    fecha_hasta: str = None,
    account: str = "CA$",
    force_refresh: bool = False,
) -> dict:
    """
    Get Banco Galicia account transactions with a financial summary.
    Scrapes live from Banco Galicia Online Banking if cache is empty or force_refresh=True.

    account: Account fragment to match (default "CA$" for peso checking account).
    fecha_desde / fecha_hasta: Filter cached results by date (YYYY-MM-DD).
                               If omitted, returns all cached transactions for the account.

    Returns:
    - transactions: list of {fecha, descripcion, monto, tipo (ingreso/egreso)}
    - summary: {ingresos_total, egresos_total, neto, count}

    Note: Live scraping requires GALICIA_USER and GALICIA_PASS in .env and takes ~30s.
    """
    from services.arca_db import get_banco_transactions as db_get
    from services.banco_galicia_scraper import get_savings_account_statements

    if not force_refresh:
        cached = db_get(account, fecha_desde, fecha_hasta)
        if cached:
            ingresos = sum(t["monto"] for t in cached if t.get("monto", 0) > 0)
            egresos = sum(t["monto"] for t in cached if t.get("monto", 0) < 0)
            return {
                "transactions": cached,
                "summary": {
                    "ingresos_total": round(ingresos, 2),
                    "egresos_total": round(egresos, 2),
                    "neto": round(ingresos + egresos, 2),
                    "count": len(cached),
                },
                **_meta("cache", len(cached)),
            }

    galicia_user = os.getenv("GALICIA_USER", "")
    galicia_pass = os.getenv("GALICIA_PASS", "")
    if not galicia_user or not galicia_pass:
        return {
            "error": "No cached data. Set GALICIA_USER and GALICIA_PASS in .env to scrape live.",
            "transactions": [],
            **_meta("error", 0),
        }

    try:
        result = await get_savings_account_statements(
            username=galicia_user,
            password=galicia_pass,
            account_fragment=account,
            export_csv=False,
        )
        transactions = result.get("transactions", [])
        ingresos = sum(t["monto"] for t in transactions if t.get("monto", 0) > 0)
        egresos = sum(t["monto"] for t in transactions if t.get("monto", 0) < 0)

        # Apply date filter if provided
        if fecha_desde or fecha_hasta:
            transactions = [
                t for t in transactions
                if (not fecha_desde or t.get("fecha", "") >= fecha_desde)
                and (not fecha_hasta or t.get("fecha", "") <= fecha_hasta)
            ]

        return {
            "transactions": transactions,
            "summary": {
                "ingresos_total": round(ingresos, 2),
                "egresos_total": round(egresos, 2),
                "neto": round(ingresos + egresos, 2),
                "count": len(transactions),
            },
            **_meta("live", len(transactions)),
        }
    except Exception as e:
        cached = db_get(account, fecha_desde, fecha_hasta)
        if cached:
            return {"transactions": cached, "count": len(cached), **_meta("cache_fallback", len(cached), error=str(e))}
        return {"error": str(e), "transactions": [], **_meta("error", 0)}
```

**Step 2: Verify all 14 tools are registered**

```bash
python -c "
import sys; sys.path.insert(0, 'arca-prototype/backend')
from mcp_server import mcp
names = sorted([t.name for t in mcp._tool_manager.list_tools()])
print(f'Total tools: {len(names)}')
for n in names: print(f'  - {n}')
assert len(names) == 14, f'Expected 14 tools, got {len(names)}'
print('All 14 tools registered!')
"
```

Expected output:
```
Total tools: 14
  - enrich_cuit
  - generate_libro_iva
  - get_bank_transactions
  - get_colppy_comprobantes
  - get_colppy_empresas
  - get_comprobantes
  - get_notificaciones
  - get_representados
  - get_retenciones
  - ping
  - reconcile_arca_vs_colppy
  - reconcile_retenciones_vs_comprobantes
  - search_company_by_name
  - search_invoices
  - test_wsaa_auth
All 14 tools registered!
```

**Step 3: Commit**

```bash
git add arca-prototype/backend/mcp_server.py
git commit -m "feat(mcp): add get_bank_transactions tool — all 14 tools complete"
```

---

## Task 12: Create mcp_config.json and register with Claude Desktop

**Files:**
- Create: `arca-prototype/mcp_config.json`

**Step 1: Create the config file**

```json
{
  "_comment": "Add the 'arca' block to your Claude Desktop MCP config at: ~/Library/Application Support/Claude/claude_desktop_config.json",
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

**Step 2: Add the arca block to Claude Desktop's actual config**

Open `~/Library/Application Support/Claude/claude_desktop_config.json` and merge in the `arca` block under `mcpServers`. If the file doesn't exist, create it with the content above (just the inner `mcpServers` part).

**Step 3: Restart Claude Desktop**

Quit and relaunch Claude Desktop. Open a new conversation and type:

```
Use the ping tool from arca
```

Expected: Claude calls `ping` and returns the server status with your configured CUIT.

**Step 4: Test a real tool**

```
Use get_comprobantes to fetch recibidos for January 2026 from cache
```

Expected: Claude calls `get_comprobantes(fecha_desde="2026-01-01", fecha_hasta="2026-01-31", direccion="recibidos")` and returns the cached data.

**Step 5: Commit the config file**

```bash
git add arca-prototype/mcp_config.json
git commit -m "feat(mcp): add mcp_config.json for Claude Desktop registration"
```

---

## Task 13: Run all tests and verify

**Step 1: Run the full test suite**

```bash
cd arca-prototype
pytest backend/tests/ -v
```

Expected: All tests pass. Note: tests that mock ARCA/Playwright services should all pass without a live connection.

**Step 2: Final tool count check**

```bash
python -c "
import sys; sys.path.insert(0, 'arca-prototype/backend')
from mcp_server import mcp
tools = mcp._tool_manager.list_tools()
print(f'{len(tools)} tools registered')
for t in tools:
    print(f'  {t.name}: {t.description[:60]}...')
"
```

**Step 3: Create tests/__init__.py if missing**

```bash
touch arca-prototype/backend/tests/__init__.py
```

**Step 4: Commit**

```bash
git add arca-prototype/backend/tests/__init__.py
git commit -m "test(mcp): finalize test suite for all MCP tools"
```

---

## Summary

| Task | Tools added | Status |
|------|-------------|--------|
| 1 | — | Add fastmcp dependency |
| 2 | `ping` | Skeleton + startup verify |
| 3 | `get_notificaciones` | ARCA DFE notifications |
| 4 | `get_comprobantes` | ARCA invoices (recibidos/emitidos) |
| 5 | `get_retenciones` | ARCA retenciones/percepciones |
| 6 | `get_representados`, `test_wsaa_auth` | Representados + WSAA cert test |
| 7 | `generate_libro_iva` | AFIP Libro IVA Digital ZIP |
| 8 | `get_colppy_empresas`, `get_colppy_comprobantes` | Colppy ERP |
| 9 | `reconcile_arca_vs_colppy`, `reconcile_retenciones_vs_comprobantes`, `search_invoices` | Reconciliation + AI search |
| 10 | `enrich_cuit`, `search_company_by_name` | CUIT enrichment + name→CUIT |
| 11 | `get_bank_transactions` | Banco Galicia |
| 12 | — | Claude Desktop registration |
| 13 | — | Final test run |
