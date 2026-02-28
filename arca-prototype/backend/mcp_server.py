#!/usr/bin/env python3
"""
ARCA MCP Server — Model Context Protocol interface for ARCA tax tools.

Exposes 14 tools + ping for Claude Desktop, Cursor, and other MCP clients:

ARCA/AFIP (6):
  - get_comprobantes: AFIP invoices (emitidos/recibidos)
  - get_retenciones: retenciones/percepciones from Mirequa
  - get_notificaciones: DFE notifications
  - get_representados: list CUITs this account represents
  - generate_libro_iva: generate AFIP Libro IVA ZIP
  - test_wsaa_auth: test X.509 certificate auth

Colppy (2):
  - get_colppy_empresas: list companies
  - get_colppy_comprobantes: invoices (venta/compra)

Reconciliation (3):
  - reconcile_arca_vs_colppy: cross-reference ARCA vs Colppy
  - reconcile_retenciones_vs_comprobantes: retenciones vs invoices
  - search_invoices: LLM-powered natural language search

CUIT Enrichment (2):
  - enrich_cuit: AFIP live + RNS dataset combined lookup
  - search_company_by_name: name-to-CUIT from 1.24M companies

Banco Galicia (1):
  - get_bank_transactions: bank transaction extraction

Usage:
    /opt/homebrew/bin/python3.11 arca-prototype/backend/mcp_server.py

MCP config (Claude Desktop / Cursor):
    "arca": {
      "command": "/opt/homebrew/bin/python3.11",
      "args": ["arca-prototype/backend/mcp_server.py"],
      "cwd": "/Users/virulana/openai-cookbook"
    }
"""
import asyncio
import base64
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — must happen before any local imports
# ---------------------------------------------------------------------------

# arca-prototype/backend/mcp_server.py  ->  arca-prototype/
ARCA_ROOT = Path(__file__).resolve().parents[1]
# arca-prototype/backend/  (for `from backend.services...` used by reconciliation modules)
BACKEND_PARENT = ARCA_ROOT
# openai-cookbook/  (repo root — for tools/scripts/)
REPO_ROOT = ARCA_ROOT.parent

# Insert paths so local imports resolve correctly
for p in [str(BACKEND_PARENT), str(REPO_ROOT), str(REPO_ROOT / "tools" / "scripts")]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# Load .env from arca-prototype/.env
# ---------------------------------------------------------------------------

_env_path = ARCA_ROOT / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path, override=False)
    except ImportError:
        # Fallback: minimal parser if python-dotenv not installed
        for line in _env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value

# ---------------------------------------------------------------------------
# Configuration from env
# ---------------------------------------------------------------------------

ARCA_CUIT = os.getenv("ARCA_CUIT", "").strip()
ARCA_PASSWORD = os.getenv("ARCA_PASSWORD", "").strip()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("arca-mcp")

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("arca")

# ---------------------------------------------------------------------------
# Lazy singletons for heavy modules (avoid import-time side effects)
# ---------------------------------------------------------------------------

_rns_name_searcher = None


def _get_rns_name_searcher():
    """Lazy-initialize RNSNameSearch (~12s first call, cached after)."""
    global _rns_name_searcher
    if _rns_name_searcher is None:
        from rns_name_search import RNSNameSearch
        _rns_name_searcher = RNSNameSearch()
    return _rns_name_searcher


# ---------------------------------------------------------------------------
# Helper: build _meta dict
# ---------------------------------------------------------------------------

def _meta(source: str, count: int, cuit: str = "", fetched_at: str | None = None) -> dict:
    """Build standard _meta dict for tool responses."""
    return {
        "source": source,
        "fetched_at": fetched_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "count": count,
        "cuit": cuit,
    }


def _clean_cuit(cuit: str) -> str:
    """Return cleaned digits-only CUIT string."""
    return "".join(c for c in cuit if c.isdigit())


def _get_arca_creds(arca_cuit: str | int = "", arca_password: str = "") -> tuple[str, str]:
    """Resolve ARCA credentials: use per-request params if provided, else fall back to env vars.

    Returns (login_cuit, password) where login_cuit is a cleaned 11-digit string.
    """
    raw = str(arca_cuit).strip() if arca_cuit else ARCA_CUIT
    password = str(arca_password).strip() if arca_password else ARCA_PASSWORD
    cuit_clean = "".join(c for c in raw if c.isdigit())
    return cuit_clean, password


def _resolve_entity_cuit(login_cuit: str) -> str:
    """Resolve the CUIT of the active representado for a given login CUIT.

    Reads the representados table from SQLite cache. If representados exist
    for this login CUIT, returns the first one (index 0). If no representados
    are cached, returns the login CUIT itself.

    Called per-request (no global cache). SQLite lookup is sub-millisecond.
    """
    if len(login_cuit) != 11:
        return login_cuit

    try:
        from backend.services import arca_db
        reps = arca_db.get_representados(login_cuit)
        if reps:
            resolved = "".join(c for c in reps[0].get("cuit", "") if c.isdigit())
            if len(resolved) == 11:
                logger.info(
                    "Resolved entity CUIT: %s (%s) for login %s",
                    resolved, reps[0].get("nombre", "?"), login_cuit,
                )
                return resolved
    except Exception as e:
        logger.warning("Could not resolve entity CUIT for %s: %s", login_cuit, e)

    return login_cuit


# ═══════════════════════════════════════════════════════════════════════════
# TOOL: ping
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def ping(arca_cuit: str | int = "") -> dict:
    """Health check. Returns server status, active CUIT, entity CUIT, and timestamp.

    Args:
        arca_cuit: Optional ARCA login CUIT. Falls back to ARCA_CUIT env var if not provided.
    """
    login_cuit, _ = _get_arca_creds(arca_cuit)
    entity_cuit = _resolve_entity_cuit(login_cuit)
    return {
        "status": "ok",
        "server": "arca-mcp",
        "login_cuit": login_cuit if len(login_cuit) == 11 else None,
        "entity_cuit": entity_cuit if len(entity_cuit) == 11 else None,
        "credentials_source": "parameter" if str(arca_cuit).strip() else "env",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# ═══════════════════════════════════════════════════════════════════════════
# ARCA/AFIP TOOLS (6)
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_comprobantes(
    fecha_desde: str,
    fecha_hasta: str,
    direccion: str = "recibidos",
    force_refresh: bool = False,
    arca_cuit: str | int = "",
    arca_password: str = "",
) -> dict:
    """Fetch AFIP invoices (comprobantes) for a given CUIT.

    Cache-first: checks SQLite cache, calls ARCA Playwright scraper only if
    cache is empty or force_refresh=True. Dates in YYYY-MM-DD format.

    Args:
        fecha_desde: Start date (YYYY-MM-DD)
        fecha_hasta: End date (YYYY-MM-DD)
        direccion: "recibidos" (purchase invoices) or "emitidos" (sales invoices)
        force_refresh: If True, bypass cache and fetch live from ARCA
        arca_cuit: ARCA login CUIT. Falls back to ARCA_CUIT env var if not provided.
        arca_password: ARCA Clave Fiscal. Falls back to ARCA_PASSWORD env var if not provided.
                      Note: transmitted in MCP protocol and may be logged by the client. Prefer env vars for persistent setups.
    """
    from backend.services import arca_db
    from backend.services.comprobantes_api import (
        get_comprobantes_recibidos,
        get_comprobantes_emitidos,
    )

    login_cuit, password = _get_arca_creds(arca_cuit, arca_password)
    entity_cuit = _resolve_entity_cuit(login_cuit)
    if len(entity_cuit) != 11:
        return {"error": "ARCA CUIT not configured (need 11 digits)", "_meta": _meta("error", 0)}

    db_dir = "R" if direccion.lower().startswith("r") else "E"

    # Cache-first
    if not force_refresh:
        items, fetched_at = arca_db.get_comprobantes(entity_cuit, db_dir, fecha_desde, fecha_hasta)
        if items:
            return {
                "comprobantes": items,
                "_meta": _meta("cache", len(items), entity_cuit, fetched_at),
            }

    # Live fetch
    if not password:
        # Fall back to cache even if empty
        items, fetched_at = arca_db.get_comprobantes(entity_cuit, db_dir, fecha_desde, fecha_hasta)
        return {
            "comprobantes": items,
            "warning": "ARCA password not set; returning cache only",
            "_meta": _meta("cache", len(items), entity_cuit, fetched_at),
        }

    # Convert YYYY-MM-DD -> DD/MM/YYYY for scraper
    try:
        d_desde = datetime.strptime(fecha_desde, "%Y-%m-%d").strftime("%d/%m/%Y")
        d_hasta = datetime.strptime(fecha_hasta, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError as e:
        return {"error": f"Invalid date format (expected YYYY-MM-DD): {e}"}

    try:
        if db_dir == "R":
            result = await get_comprobantes_recibidos(
                cuit=login_cuit, password=password,
                fecha_desde=d_desde, fecha_hasta=d_hasta,
                id_contribuyente=0,
            )
        else:
            result = await get_comprobantes_emitidos(
                cuit=login_cuit, password=password,
                fecha_desde=d_desde, fecha_hasta=d_hasta,
                id_contribuyente=0,
            )
    except Exception as e:
        logger.error("ARCA scraper error: %s", e)
        # Fall back to cache
        items, fetched_at = arca_db.get_comprobantes(entity_cuit, db_dir, fecha_desde, fecha_hasta)
        return {
            "comprobantes": items,
            "warning": f"Live fetch failed ({e}); returning cache",
            "_meta": _meta("cache_fallback", len(items), entity_cuit, fetched_at),
        }

    if not result.get("success"):
        # Fall back to cache
        items, fetched_at = arca_db.get_comprobantes(entity_cuit, db_dir, fecha_desde, fecha_hasta)
        return {
            "comprobantes": items,
            "warning": f"Live fetch failed: {result.get('error', 'unknown')}; returning cache",
            "_meta": _meta("cache_fallback", len(items), entity_cuit, fetched_at),
        }

    # Save to cache
    scraped = result.get("comprobantes", [])
    cuit_repr = result.get("cuit_representado") or entity_cuit
    if scraped:
        arca_db.save_comprobantes(cuit_repr, scraped, direccion=db_dir)

    # Re-read from cache for consistent format
    items, fetched_at = arca_db.get_comprobantes(entity_cuit, db_dir, fecha_desde, fecha_hasta)
    return {
        "comprobantes": items,
        "_meta": _meta("live", len(items), entity_cuit, fetched_at),
    }


@mcp.tool()
async def get_retenciones(
    fecha_desde: str,
    fecha_hasta: str,
    tipo_operacion: str = "ambos",
    force_refresh: bool = False,
    arca_cuit: str | int = "",
    arca_password: str = "",
) -> dict:
    """Fetch retenciones/percepciones from ARCA Mis Retenciones (Mirequa).

    Cache-first: checks SQLite cache, calls ARCA Playwright scraper only if
    cache is empty or force_refresh=True. Dates in YYYY-MM-DD format.

    Args:
        fecha_desde: Start date (YYYY-MM-DD)
        fecha_hasta: End date (YYYY-MM-DD)
        tipo_operacion: "retencion", "percepcion", or "ambos" (default: "ambos" fetches both)
        force_refresh: If True, bypass cache and fetch live from ARCA
        arca_cuit: ARCA login CUIT. Falls back to ARCA_CUIT env var if not provided.
        arca_password: ARCA Clave Fiscal. Falls back to ARCA_PASSWORD env var if not provided.
                      Note: transmitted in MCP protocol and may be logged by the client. Prefer env vars for persistent setups.
    """
    from backend.services import arca_db
    from backend.services.retenciones_api import download_retenciones

    login_cuit, password = _get_arca_creds(arca_cuit, arca_password)
    entity_cuit = _resolve_entity_cuit(login_cuit)
    if len(entity_cuit) != 11:
        return {"error": "ARCA CUIT not configured (need 11 digits)", "_meta": _meta("error", 0)}

    # Determine which types to fetch
    tipo = tipo_operacion.lower().strip()
    if tipo == "ambos":
        tipos_to_fetch = ["retencion", "percepcion"]
    elif tipo.startswith("ret"):
        tipos_to_fetch = ["retencion"]
    elif tipo.startswith("percep"):
        tipos_to_fetch = ["percepcion"]
    else:
        return {"error": f"Invalid tipo_operacion '{tipo_operacion}'. Use 'retencion', 'percepcion', or 'ambos'."}

    # Cache-first
    if not force_refresh:
        items, fetched_at = arca_db.get_retenciones(entity_cuit, fecha_desde, fecha_hasta)
        if items:
            return {
                "retenciones": items,
                "_meta": _meta("cache", len(items), entity_cuit, fetched_at),
            }

    # Live fetch
    if not password:
        items, fetched_at = arca_db.get_retenciones(entity_cuit, fecha_desde, fecha_hasta)
        return {
            "retenciones": items,
            "warning": "ARCA password not set; returning cache only",
            "_meta": _meta("cache", len(items), entity_cuit, fetched_at),
        }

    # Convert dates for scraper (DD/MM/YYYY)
    try:
        d_desde = datetime.strptime(fecha_desde, "%Y-%m-%d").strftime("%d/%m/%Y")
        d_hasta = datetime.strptime(fecha_hasta, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError as e:
        return {"error": f"Invalid date format (expected YYYY-MM-DD): {e}"}

    # Fetch each tipo_operacion (one or two scraper runs)
    all_fetched: list[dict] = []
    fetch_errors: list[str] = []
    for tipo_op in tipos_to_fetch:
        try:
            result = await download_retenciones(
                cuit=login_cuit,
                password=password,
                fecha_desde=d_desde,
                fecha_hasta=d_hasta,
                id_contribuyente=0,
                cuit_representado=entity_cuit,
                tipo_operacion=tipo_op,
            )
            if result.get("success"):
                fetched = result.get("retenciones", [])
                logger.info("Fetched %d %s(es) from Mirequa", len(fetched), tipo_op)
                all_fetched.extend(fetched)
            else:
                fetch_errors.append(f"{tipo_op}: {result.get('error', 'unknown')}")
        except Exception as e:
            logger.error("Retenciones scraper error (%s): %s", tipo_op, e)
            fetch_errors.append(f"{tipo_op}: {e}")

    if not all_fetched and fetch_errors:
        items, fetched_at = arca_db.get_retenciones(entity_cuit, fecha_desde, fecha_hasta)
        return {
            "retenciones": items,
            "warning": f"Live fetch failed: {'; '.join(fetch_errors)}; returning cache",
            "_meta": _meta("cache_fallback", len(items), entity_cuit, fetched_at),
        }

    # Save to cache
    if all_fetched:
        arca_db.save_retenciones(entity_cuit, all_fetched)

    # Re-read from cache
    items, fetched_at = arca_db.get_retenciones(entity_cuit, fecha_desde, fecha_hasta)
    warnings = {}
    if fetch_errors:
        warnings["partial_errors"] = fetch_errors
    return {
        "retenciones": items,
        **warnings,
        "_meta": _meta("live", len(items), entity_cuit, fetched_at),
    }


@mcp.tool()
async def get_notificaciones(
    force_refresh: bool = False,
    cuit_representado: str | None = None,
    arca_cuit: str | int = "",
    arca_password: str = "",
) -> dict:
    """Fetch DFE (Domicilio Fiscal Electronico) notifications from ARCA.

    Cache-first: checks SQLite cache, calls ARCA Playwright scraper only if
    cache is empty or force_refresh=True. Returns notification list with
    full message content, classification, and PDF attachment status.

    Args:
        force_refresh: If True, bypass cache and fetch live from ARCA
        cuit_representado: CUIT of the entity to fetch notifications for.
                          If None, uses the first representado for the login CUIT.
        arca_cuit: ARCA login CUIT. Falls back to ARCA_CUIT env var if not provided.
        arca_password: ARCA Clave Fiscal. Falls back to ARCA_PASSWORD env var if not provided.
                      Note: transmitted in MCP protocol and may be logged by the client. Prefer env vars for persistent setups.
    """
    from backend.services import arca_db
    from backend.services.notifications_api import get_notifications_with_content

    login_cuit, password = _get_arca_creds(arca_cuit, arca_password)
    entity_cuit = _clean_cuit(cuit_representado) if cuit_representado else _resolve_entity_cuit(login_cuit)
    if len(entity_cuit) != 11:
        return {"error": "CUIT must be 11 digits", "_meta": _meta("error", 0)}

    # Cache-first
    if not force_refresh:
        items, fetched_at = arca_db.get_notifications(entity_cuit)
        if items:
            return {
                "notifications": items,
                "_meta": _meta("cache", len(items), entity_cuit, fetched_at),
            }

    # Live fetch
    if not login_cuit or not password:
        items, fetched_at = arca_db.get_notifications(entity_cuit)
        return {
            "notifications": items,
            "warning": "ARCA credentials not configured; returning cache only",
            "_meta": _meta("cache", len(items), entity_cuit, fetched_at),
        }

    try:
        result = await get_notifications_with_content(
            cuit=login_cuit,
            password=password,
            cuit_representado=entity_cuit,
        )
    except Exception as e:
        logger.error("Notifications fetch error: %s", e)
        items, fetched_at = arca_db.get_notifications(entity_cuit)
        return {
            "notifications": items,
            "warning": f"Live fetch failed ({e}); returning cache",
            "_meta": _meta("cache_fallback", len(items), entity_cuit, fetched_at),
        }

    if not result.get("success"):
        items, fetched_at = arca_db.get_notifications(entity_cuit)
        return {
            "notifications": items,
            "warning": f"Live fetch failed: {result.get('error', 'unknown')}; returning cache",
            "_meta": _meta("cache_fallback", len(items), entity_cuit, fetched_at),
        }

    # Data is saved to cache inside get_notifications_with_content
    notifs = result.get("notifications", [])
    # Strip pdf_content from response (binary, not useful for LLM)
    for n in notifs:
        n.pop("pdf_content", None)

    return {
        "notifications": notifs,
        "_meta": _meta("live", len(notifs), entity_cuit),
    }


@mcp.tool()
async def get_representados(
    force_refresh: bool = False,
    arca_cuit: str | int = "",
    arca_password: str = "",
) -> dict:
    """List CUITs this ARCA account can act on behalf of (representados).

    Cache-first: checks SQLite cache, calls ARCA DFE API only if cache is
    empty or force_refresh=True.

    Args:
        force_refresh: If True, bypass cache and fetch live from ARCA
        arca_cuit: ARCA login CUIT. Falls back to ARCA_CUIT env var if not provided.
        arca_password: ARCA Clave Fiscal. Falls back to ARCA_PASSWORD env var if not provided.
                      Note: transmitted in MCP protocol and may be logged by the client. Prefer env vars for persistent setups.
    """
    from backend.services import arca_db
    from backend.services.notifications_api import get_representados as api_get_representados

    login_cuit, password = _get_arca_creds(arca_cuit, arca_password)
    if len(login_cuit) != 11:
        return {"error": "ARCA CUIT not configured (need 11 digits)", "_meta": _meta("error", 0)}

    # Cache-first
    if not force_refresh:
        items = arca_db.get_representados(login_cuit)
        if items:
            return {
                "representados": items,
                "_meta": _meta("cache", len(items), login_cuit),
            }

    # Live fetch
    if not password:
        items = arca_db.get_representados(login_cuit)
        return {
            "representados": items,
            "warning": "ARCA password not set; returning cache only",
            "_meta": _meta("cache", len(items), login_cuit),
        }

    try:
        result = await api_get_representados(cuit=login_cuit, password=password)
    except Exception as e:
        logger.error("Representados fetch error: %s", e)
        items = arca_db.get_representados(login_cuit)
        return {
            "representados": items,
            "warning": f"Live fetch failed ({e}); returning cache",
            "_meta": _meta("cache_fallback", len(items), login_cuit),
        }

    if not result.get("success"):
        items = arca_db.get_representados(login_cuit)
        return {
            "representados": items,
            "warning": f"Live fetch failed: {result.get('error', 'unknown')}; returning cache",
            "_meta": _meta("cache_fallback", len(items), login_cuit),
        }

    # Data is saved to cache inside api_get_representados
    reps = result.get("representados", [])
    return {
        "representados": reps,
        "_meta": _meta("live", len(reps), login_cuit),
    }


@mcp.tool()
async def generate_libro_iva(
    fecha_desde: str,
    fecha_hasta: str,
    tipo: str = "ventas",
    arca_cuit: str | int = "",
) -> dict:
    """Generate AFIP Libro IVA Digital ZIP from cached comprobantes.

    Reads comprobantes from SQLite cache and converts them to AFIP's
    fixed-position format (cabecera + alicuotas), packaged as a ZIP.
    The ZIP is base64-encoded in the response for transport.

    Args:
        fecha_desde: Start date (YYYY-MM-DD)
        fecha_hasta: End date (YYYY-MM-DD)
        tipo: "ventas" (sales, uses emitidos) or "compras" (purchases, uses recibidos)
        arca_cuit: ARCA login CUIT. Falls back to ARCA_CUIT env var if not provided.
    """
    from backend.services import arca_db
    from backend.services.libro_iva_converter import (
        build_libro_iva_zip,
        comprobantes_to_libro_iva,
    )

    login_cuit, _ = _get_arca_creds(arca_cuit)
    entity_cuit = _resolve_entity_cuit(login_cuit)
    if len(entity_cuit) != 11:
        return {"error": "ARCA CUIT not configured (need 11 digits)"}

    db_dir = "E" if tipo.lower().startswith("v") else "R"
    items, fetched_at = arca_db.get_comprobantes(entity_cuit, db_dir, fecha_desde, fecha_hasta)

    if not items:
        return {
            "error": f"No comprobantes in cache for {fecha_desde} to {fecha_hasta} ({tipo}). "
                     "Fetch them first with get_comprobantes.",
            "_meta": _meta("cache", 0, entity_cuit),
        }

    cabeceras, alicuotas = comprobantes_to_libro_iva(items, tipo=tipo)
    zip_bytes = build_libro_iva_zip(
        cabeceras, alicuotas, tipo=tipo,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
    )

    return {
        "success": True,
        "tipo": tipo,
        "comprobantes_count": len(items),
        "cabecera_lines": len(cabeceras),
        "alicuota_lines": len(alicuotas),
        "zip_base64": base64.b64encode(zip_bytes).decode("ascii"),
        "zip_size_bytes": len(zip_bytes),
        "_meta": _meta("generated", len(items), entity_cuit, fetched_at),
    }


@mcp.tool()
def test_wsaa_auth() -> dict:
    """Test AFIP WSAA X.509 certificate authentication.

    Verifies that ARCA_CERT_PATH and ARCA_KEY_PATH are configured and
    that a valid token/sign pair can be obtained from WSAA.
    """
    from backend.services.wsaa_client import get_credentials

    try:
        creds = get_credentials(service="veconsumerws")
        return {
            "success": True,
            "message": "WSAA authentication OK. Token obtained.",
            "token_preview": creds["token"][:20] + "..." if creds.get("token") else None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# COLPPY TOOLS (2)
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_colppy_empresas() -> dict:
    """List all companies accessible via Colppy API.

    Performs login -> list_empresas -> logout. Requires COLPPY_* env vars.
    Returns company IDs, names, CUITs needed for other Colppy operations.
    """
    from backend.services import colppy_api

    login_result = await colppy_api.login()
    if not login_result["success"]:
        return {"success": False, "error": f"Colppy login failed: {login_result['message']}"}

    clave = login_result["data"]["claveSesion"]
    try:
        empresas_result = await colppy_api.list_empresas(clave)
    finally:
        await colppy_api.logout(clave)

    if not empresas_result["success"]:
        return {"success": False, "error": f"list_empresas failed: {empresas_result.get('message', '')}"}

    empresas = empresas_result.get("data") or []
    # Simplify for LLM consumption
    simplified = [
        {
            "id": e.get("IdEmpresa"),
            "nombre": e.get("Nombre"),
            "razon_social": e.get("razonSocial"),
            "cuit": e.get("CUIT"),
            "activa": e.get("activa"),
        }
        for e in (empresas if isinstance(empresas, list) else [empresas])
    ]

    return {
        "success": True,
        "empresas": simplified,
        "_meta": _meta("live", len(simplified)),
    }


@mcp.tool()
async def get_colppy_comprobantes(
    id_empresa: str,
    from_date: str,
    to_date: str,
    tipo: str = "venta",
) -> dict:
    """Fetch invoices from Colppy API (facturas de venta or compra).

    Performs login -> list call -> logout per request.
    Dates in YYYY-MM-DD format.

    Args:
        id_empresa: Colppy company ID (from get_colppy_empresas)
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        tipo: "venta" for sales invoices, "compra" for purchase invoices
    """
    from backend.services import colppy_api

    login_result = await colppy_api.login()
    if not login_result["success"]:
        return {"success": False, "error": f"Colppy login failed: {login_result['message']}"}

    clave = login_result["data"]["claveSesion"]
    try:
        if tipo.lower().startswith("c"):
            result = await colppy_api.list_comprobantes_compra(
                clave, id_empresa, from_date, to_date,
            )
        else:
            result = await colppy_api.list_comprobantes_venta(
                clave, id_empresa, from_date, to_date,
            )
    finally:
        await colppy_api.logout(clave)

    if not result["success"]:
        return {"success": False, "error": result.get("message", "unknown error")}

    items = result.get("data") or []
    if not isinstance(items, list):
        items = [items]

    return {
        "success": True,
        "tipo": tipo,
        "total": len(items),
        "comprobantes": items,
        "_meta": _meta("live", len(items)),
    }


# ═══════════════════════════════════════════════════════════════════════════
# RECONCILIATION TOOLS (3)
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def reconcile_arca_vs_colppy(
    id_empresa: str,
    fecha_desde: str,
    fecha_hasta: str,
    direccion: str = "emitidos",
    arca_cuit: str | int = "",
) -> dict:
    """Cross-reference ARCA comprobantes vs Colppy invoices by CAE or invoice number.

    For emitidos (sales): matches by CAE (globally unique AFIP code).
    For recibidos (purchases): matches by supplier CUIT + invoice number.

    ARCA data comes from SQLite cache (auto-fetches from ARCA if empty).
    Colppy data is fetched live via API.

    Returns summary counts and detailed discrepancy list:
    matched, amount_mismatch, only_arca, only_colppy, missing_cae, duplicate_cae.

    Args:
        id_empresa: Colppy company ID
        fecha_desde: Start date (YYYY-MM-DD)
        fecha_hasta: End date (YYYY-MM-DD)
        direccion: "emitidos" (sales) or "recibidos" (purchases)
        arca_cuit: ARCA login CUIT. Falls back to ARCA_CUIT env var if not provided.
    """
    login_cuit, _ = _get_arca_creds(arca_cuit)
    entity_cuit = _resolve_entity_cuit(login_cuit)
    if len(entity_cuit) != 11:
        return {"error": "ARCA CUIT not configured (need 11 digits)"}

    if direccion.lower().startswith("e"):
        from backend.services.reconciliacion_emitidos import reconcile_emitidos
        result = await reconcile_emitidos(
            cuit_representado=entity_cuit,
            id_empresa=id_empresa,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
    else:
        # For recibidos, use the stream version but collect all events
        from backend.services.reconciliacion_recibidos import reconcile_recibidos_stream
        result = None
        async for sse_line in reconcile_recibidos_stream(
            cuit_representado=entity_cuit,
            id_empresa=id_empresa,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        ):
            # Parse SSE line: "data: {...}\n\n"
            if sse_line.startswith("data: "):
                try:
                    event = json.loads(sse_line[6:].strip())
                    if event.get("type") == "result":
                        result = event.get("data", {})
                    elif event.get("type") == "error":
                        return {"success": False, "error": event.get("message", "unknown")}
                except json.JSONDecodeError:
                    pass
        if result is None:
            return {"success": False, "error": "Reconciliation produced no result"}

    return result


@mcp.tool()
async def reconcile_retenciones_vs_comprobantes(
    fecha_desde: str,
    fecha_hasta: str,
    id_empresa: str | int = "",
    arca_cuit: str | int = "",
) -> dict:
    """Cross-reference ARCA retenciones/percepciones against comprobantes recibidos.

    Both ARCA datasets come from SQLite cache. Groups retenciones by
    (agent CUIT, month) and matches against comprobantes from the
    same supplier in the same period.

    When id_empresa is provided, also fetches Colppy purchase invoices
    and compares percepciones by supplier CUIT — showing dates, amounts,
    and document numbers for easy side-by-side comparison.

    Returns per-period breakdown with match status (matched, orphan, no_data),
    DDJJ-ready totals, and (if Colppy data available) percepciones comparison.

    Args:
        fecha_desde: Start date (YYYY-MM-DD)
        fecha_hasta: End date (YYYY-MM-DD)
        id_empresa: Colppy company ID (optional). When set, adds Colppy
                    percepciones comparison per agent CUIT.
        arca_cuit: ARCA login CUIT. Falls back to ARCA_CUIT env var if not provided.
    """
    import re
    from collections import defaultdict

    from backend.services import arca_db, colppy_api

    id_empresa = str(id_empresa) if id_empresa else ""
    from backend.services.comprobantes_api import TIPO_COMPROBANTE
    from backend.services.reconciliacion_service import reconcile_retenciones

    login_cuit, _ = _get_arca_creds(arca_cuit)
    entity_cuit = _resolve_entity_cuit(login_cuit)
    if len(entity_cuit) != 11:
        return {"error": "ARCA CUIT not configured (need 11 digits)"}

    retenciones, ret_fetched = arca_db.get_retenciones(entity_cuit, fecha_desde, fecha_hasta)
    comprobantes, comp_fetched = arca_db.get_comprobantes(entity_cuit, "R", fecha_desde, fecha_hasta)

    # Optionally fetch Colppy percepciones for side-by-side comparison
    colppy_percepciones: dict[str, list[dict]] | None = None
    colppy_meta: dict[str, Any] = {}

    if id_empresa:
        try:
            login_result = await colppy_api.login()
            if login_result and login_result.get("success"):
                clave = login_result["data"]["claveSesion"]
                try:
                    # Fetch proveedores for CUIT resolution
                    prov_result = await colppy_api.list_proveedores(
                        clave, id_empresa, only_active=False,
                    )
                    cuit_map: dict[int, str] = {}
                    nombre_map: dict[int, str] = {}
                    if prov_result.get("success"):
                        for p in (prov_result.get("data") or []):
                            pid = p.get("idProveedor")
                            if pid is not None:
                                cuit_map[pid] = re.sub(r"[^0-9]", "", str(p.get("CUIT", "")))
                                nombre_map[pid] = p.get("RazonSocial", "")

                    # Fetch comprobantes de compra
                    compra_result = await colppy_api.list_comprobantes_compra(
                        clave, id_empresa, fecha_desde, fecha_hasta,
                    )
                    if compra_result.get("success"):
                        colppy_percepciones = defaultdict(list)

                        def _sf(raw):
                            try:
                                return round(float(raw or 0), 2)
                            except (ValueError, TypeError):
                                return 0.0

                        for v in (compra_result.get("data") or []):
                            # Skip anuladas
                            if str(v.get("idEstadoFactura", "")) == "3":
                                continue
                            pid = v.get("idProveedor")
                            supplier_cuit = cuit_map.get(pid, "")
                            if not supplier_cuit:
                                continue

                            perc_iva = _sf(v.get("percepcionIVA", "0"))
                            perc_iibb = _sf(v.get("percepcionIIBB", "0"))
                            perc_iibb1 = _sf(v.get("percepcionIIBB1", "0"))
                            perc_iibb2 = _sf(v.get("percepcionIIBB2", "0"))
                            iibb_local = _sf(v.get("IIBBLocal", "0"))
                            iibb_otro = _sf(v.get("IIBBOtro", "0"))
                            total_perc = round(perc_iva + perc_iibb + perc_iibb1 + perc_iibb2 + iibb_local + iibb_otro, 2)

                            if total_perc == 0:
                                continue

                            tipo_id = str(v.get("idTipoComprobante", ""))
                            colppy_percepciones[supplier_cuit].append({
                                "nroFactura": v.get("nroFactura", "") or "",
                                "fechaFactura": v.get("fechaFactura", "") or "",
                                "RazonSocial": nombre_map.get(pid, v.get("RazonSocial", "")),
                                "tipo_comprobante": TIPO_COMPROBANTE.get(tipo_id, f"Tipo {tipo_id}"),
                                "totalFactura": _sf(v.get("totalFactura", "0")),
                                "percepcionIVA": perc_iva,
                                "percepcionIIBB": perc_iibb,
                                "totalPercepciones": total_perc,
                            })

                        colppy_meta = {
                            "colppy_compras_total": len(compra_result.get("data") or []),
                            "colppy_with_percepciones": sum(len(v) for v in colppy_percepciones.values()),
                            "colppy_supplier_cuits": len(colppy_percepciones),
                        }
                        colppy_percepciones = dict(colppy_percepciones)
                finally:
                    await colppy_api.logout(clave)
        except Exception as e:
            colppy_meta = {"colppy_error": str(e)}

    result = reconcile_retenciones(
        retenciones=retenciones,
        comprobantes=comprobantes,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        colppy_percepciones=colppy_percepciones,
    )

    result["_meta"] = _meta("cache", len(retenciones), entity_cuit, ret_fetched)
    result["_meta"]["retenciones_fetched_at"] = ret_fetched
    result["_meta"]["comprobantes_fetched_at"] = comp_fetched
    if colppy_meta:
        result["_meta"].update(colppy_meta)
    return result


@mcp.tool()
async def search_invoices(
    query: str,
    scope: str = "discrepancies",
    arca_cuit: str | int = "",
) -> dict:
    """Search invoices using natural language (powered by GPT-4o-mini).

    Searches over the most recent reconciliation data in cache.
    Useful for questions like: "which invoices over $100k are only in ARCA?"
    or "show me all discrepancies with EMPRESA XYZ".

    Args:
        query: Natural language search query (in Spanish or English)
        scope: "discrepancies" (search only mismatches) or "all" (include matched)
        arca_cuit: ARCA login CUIT. Falls back to ARCA_CUIT env var if not provided.
    """
    from backend.services import arca_db
    from backend.services.reconciliation_search import search_invoices_stream

    login_cuit, _ = _get_arca_creds(arca_cuit)
    entity_cuit = _resolve_entity_cuit(login_cuit)
    if len(entity_cuit) != 11:
        return {"error": "ARCA CUIT not configured (need 11 digits)"}

    # Get the most recent data from cache
    # Default to last 3 months if no specific range
    today = datetime.now()
    fecha_hasta = today.strftime("%Y-%m-%d")
    fecha_desde = (today - timedelta(days=90)).strftime("%Y-%m-%d")

    # Load both emitidos and recibidos for reconciliation context
    arca_emitidos, _ = arca_db.get_comprobantes(entity_cuit, "E", fecha_desde, fecha_hasta)
    arca_recibidos, _ = arca_db.get_comprobantes(entity_cuit, "R", fecha_desde, fecha_hasta)
    arca_items = arca_emitidos + arca_recibidos

    # Build minimal discrepancies/matched from cache (we don't have full reconciliation
    # results cached, so we pass the comprobantes as context)
    discrepancies: list[dict] = []
    matched_pairs: list[dict] = []

    # Pass comprobantes as discrepancies for search context
    for item in arca_items:
        discrepancies.append({
            "status": "cached_comprobante",
            "arca": item,
            "colppy": None,
        })

    # Collect streaming response
    full_response = ""
    caes: list[str] = []

    async for sse_line in search_invoices_stream(
        query=query,
        cuit=entity_cuit,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        scope=scope,
        conversation=[],
        discrepancies=discrepancies,
        matched_pairs=matched_pairs,
    ):
        if sse_line.startswith("data: "):
            try:
                event = json.loads(sse_line[6:].strip())
                if event.get("type") == "text":
                    full_response += event.get("content", "")
                elif event.get("type") == "matches":
                    caes = event.get("caes", [])
                elif event.get("type") == "error":
                    return {"error": event.get("content", "Search error")}
            except json.JSONDecodeError:
                pass

    return {
        "response": full_response,
        "matched_caes": caes,
        "_meta": _meta("search", len(caes), entity_cuit),
    }


# ═══════════════════════════════════════════════════════════════════════════
# CUIT ENRICHMENT TOOLS (2)
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def enrich_cuit(cuit: str) -> dict:
    """Enrich a CUIT with data from AFIP (live API) and RNS (open dataset).

    Combines two sources:
    - AFIP live lookup via TusFacturas.app: tax status, address, economic activities
    - RNS dataset (3M+ records): incorporation date, legal type, province

    Useful for lead qualification, KYC, and understanding a company's profile.

    Args:
        cuit: CUIT number (11 digits, with or without dashes)
    """
    clean = "".join(c for c in cuit if c.isdigit())
    if len(clean) != 11:
        return {"error": f"Invalid CUIT: must be 11 digits, got {len(clean)}"}

    result: dict[str, Any] = {"cuit": clean}

    # AFIP live lookup (sync, wrap in thread)
    try:
        from afip_cuit_lookup import AFIPCUITLookupService
        service = AFIPCUITLookupService()
        afip_info = await asyncio.to_thread(service.lookup_cuit, clean)
        if afip_info and not afip_info.error:
            result["afip"] = {
                "razon_social": afip_info.razon_social,
                "condicion_impositiva": afip_info.condicion_impositiva,
                "estado": afip_info.estado,
                "direccion": afip_info.direccion,
                "localidad": afip_info.localidad,
                "provincia": afip_info.provincia,
                "actividades": [
                    {
                        "descripcion": a.descripcion,
                        "id": a.id,
                        "periodo": a.periodo,
                    }
                    for a in afip_info.actividades
                ],
            }
        elif afip_info and afip_info.error:
            result["afip"] = {"error": True, "errores": afip_info.errores}
        else:
            result["afip"] = {"error": True, "errores": ["CUIT not found or API unavailable"]}
    except ValueError as e:
        result["afip"] = {"error": True, "errores": [str(e)]}
    except Exception as e:
        result["afip"] = {"error": True, "errores": [f"AFIP lookup failed: {e}"]}

    # RNS dataset lookup (sync, wrap in thread)
    try:
        from rns_dataset_lookup import RNSDatasetLookup
        rns = RNSDatasetLookup()
        rns_result = await asyncio.to_thread(rns.lookup_cuit, clean)
        if rns_result and rns_result.found:
            result["rns"] = {
                "razon_social": rns_result.razon_social,
                "creation_date": rns_result.creation_date,
                "tipo_societario": rns_result.tipo_societario,
                "provincia": rns_result.provincia,
                "actividad_descripcion": rns_result.actividad_descripcion,
            }
        else:
            result["rns"] = {"found": False}
    except Exception as e:
        result["rns"] = {"error": f"RNS lookup failed: {e}"}

    result["_meta"] = _meta("enrichment", 1, clean)
    return result


@mcp.tool()
async def search_company_by_name(
    query: str,
    provincia: str | None = None,
    limit: int = 10,
) -> dict:
    """Search for a company by name to find its CUIT (from 1.24M RNS records).

    Multi-token substring search over the Argentine RNS (Registro Nacional
    de Sociedades) dataset. Results ranked by match quality.

    First call takes ~12s to load dataset into memory; subsequent calls <100ms.

    Args:
        query: Company name to search (e.g. "panaderia martinez", "BANCO BBVA")
        provincia: Optional province filter (e.g. "Buenos Aires", "Cordoba")
        limit: Max results to return (default 10)
    """
    try:
        searcher = await asyncio.to_thread(_get_rns_name_searcher)
        results = await asyncio.to_thread(
            searcher.search, query, provincia, limit,
        )
    except FileNotFoundError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Search failed: {e}"}

    matches = [asdict(r) for r in results]
    return {
        "query": query,
        "provincia": provincia,
        "results": matches,
        "_meta": _meta("rns_dataset", len(matches)),
    }


# ═══════════════════════════════════════════════════════════════════════════
# BANCO GALICIA TOOL (1)
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_bank_transactions(
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    account: str = "CA$",
    force_refresh: bool = False,
) -> dict:
    """Fetch bank transactions from Banco Galicia savings account.

    Cache-first: checks SQLite cache, launches Playwright scraper only
    if cache is empty or force_refresh=True.

    Requires GALICIA_DNI, GALICIA_USER, GALICIA_PASS env vars.
    Dates in YYYY-MM-DD format.

    Args:
        fecha_desde: Optional start date filter (YYYY-MM-DD)
        fecha_hasta: Optional end date filter (YYYY-MM-DD)
        account: Account identifier fragment (default "CA$" = Caja de Ahorro Pesos)
        force_refresh: If True, bypass cache and scrape live from Galicia
    """
    from backend.services import arca_db
    from backend.services.banco_galicia_scraper import get_savings_account_statements

    # Cache-first
    if not force_refresh:
        items, fetched_at = arca_db.get_banco_transactions(account, fecha_desde, fecha_hasta)
        if items:
            return {
                "transactions": items,
                "_meta": _meta("cache", len(items), fetched_at=fetched_at),
            }

    # Check credentials
    if not os.getenv("GALICIA_DNI") or not os.getenv("GALICIA_USER") or not os.getenv("GALICIA_PASS"):
        items, fetched_at = arca_db.get_banco_transactions(account, fecha_desde, fecha_hasta)
        return {
            "transactions": items,
            "warning": "Banco Galicia credentials not configured; returning cache only",
            "_meta": _meta("cache", len(items), fetched_at=fetched_at),
        }

    # Live fetch via Playwright
    try:
        result = await get_savings_account_statements(
            account_fragment=account,
            export_csv=False,
        )
    except Exception as e:
        logger.error("Banco Galicia scraper error: %s", e)
        items, fetched_at = arca_db.get_banco_transactions(account, fecha_desde, fecha_hasta)
        return {
            "transactions": items,
            "warning": f"Live fetch failed ({e}); returning cache",
            "_meta": _meta("cache_fallback", len(items), fetched_at=fetched_at),
        }

    if not result.get("success"):
        items, fetched_at = arca_db.get_banco_transactions(account, fecha_desde, fecha_hasta)
        return {
            "transactions": items,
            "warning": f"Live fetch failed: {result.get('message', 'unknown')}; returning cache",
            "_meta": _meta("cache_fallback", len(items), fetched_at=fetched_at),
        }

    # Save to cache
    raw_txns = result.get("data", {}).get("transactions", [])
    if raw_txns:
        arca_db.save_banco_transactions(account, raw_txns)

    # Re-read from cache (with date filters applied)
    items, fetched_at = arca_db.get_banco_transactions(account, fecha_desde, fecha_hasta)
    return {
        "transactions": items,
        "_meta": _meta("live", len(items), fetched_at=fetched_at),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run(transport="stdio")
