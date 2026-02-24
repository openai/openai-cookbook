"""
Colppy API client — thin wrapper over Colppy's single-endpoint JSON API.

Endpoint: POST https://login.colppy.com/lib/frontera2/service.php
Protocol: JSON body with { auth, service, parameters }

Auth flow:
  1. Developer credentials (MD5'd password) in auth block
  2. iniciar_sesion with platform user (MD5'd password) → get claveSesion
  3. All subsequent calls use claveSesion in parameters.sesion

All listar_* operations require these parameters (per official wiki docs):
  - idEmpresa: str (required)
  - start: int (pagination offset, default 0)
  - limit: int (page size, default 50, max 5000 for FacturaVenta)
  - filter: list[dict] (required, even if empty: [])
  - order: dict (required, even if empty: {"field": [], "order": ""})

Date filtering uses the filter array, NOT fromDate/toDate:
  filter: [{"field": "fechaFactura", "op": ">=", "value": "2025-01-01"},
           {"field": "fechaFactura", "op": "<=", "value": "2025-12-31"}]

Documentation sources:
  - apidocs.colppy.com — 4 provisions (Usuario, Cliente, Contabilidad, Empresa)
  - Atlassian wiki CA space (page 16318473) — 15 provisions, 60+ operations
  - Operation names are CASE SENSITIVE:
      listar_facturasCompra (capital C)  vs  listar_facturasventa (lowercase)

Env vars:
  COLPPY_AUTH_USER       — Developer email (registered at api.colppy.com)
  COLPPY_AUTH_PASSWORD   — Developer password (plain text, MD5'd at runtime)
  COLPPY_USER            — Platform user email
  COLPPY_PASSWORD        — Platform user password
  COLPPY_ID_EMPRESA      — Default company ID
"""

import hashlib
import os
from typing import Any

import httpx

COLPPY_API_URL = "https://login.colppy.com/lib/frontera2/service.php"
COLPPY_TIMEOUT = 30.0
DEFAULT_PAGE_SIZE = 2000
MAX_PAGE_SIZE = 5000


def _get_credentials() -> dict[str, str]:
    """Read Colppy credentials from environment. Raises ValueError if missing."""
    required = {
        "COLPPY_AUTH_USER": os.getenv("COLPPY_AUTH_USER", ""),
        "COLPPY_AUTH_PASSWORD": os.getenv("COLPPY_AUTH_PASSWORD", ""),
        "COLPPY_USER": os.getenv("COLPPY_USER", ""),
        "COLPPY_PASSWORD": os.getenv("COLPPY_PASSWORD", ""),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise ValueError(f"Missing Colppy env vars: {', '.join(missing)}")
    return required


def _md5(text: str) -> str:
    """MD5 hash a string (Colppy API requires MD5'd passwords in both auth and parameters)."""
    return hashlib.md5(text.encode()).hexdigest()


def _auth_block(creds: dict[str, str]) -> dict[str, str]:
    """Build the auth block for every API request."""
    return {
        "usuario": creds["COLPPY_AUTH_USER"],
        "password": _md5(creds["COLPPY_AUTH_PASSWORD"]),
    }


def _check_response(data: dict[str, Any]) -> tuple[bool, str]:
    """
    Check Colppy API response for errors.
    Returns (success, message).

    Response structure:
      { "result": {"estado": 0, "mensaje": "OK"},
        "response": {"success": true, "data": ..., "message": "..."} }
    """
    result = data.get("result", {})
    if result.get("estado", -1) != 0:
        return False, result.get("mensaje", "Unknown API error")

    response = data.get("response", {})
    if not response.get("success", False):
        return False, response.get("message", "Operation failed")

    return True, "OK"


def _build_date_filter(
    from_date: str = "",
    to_date: str = "",
    field: str = "fechaFactura",
) -> list[dict[str, str]]:
    """Build filter array items for date range filtering."""
    filters: list[dict[str, str]] = []
    if from_date:
        filters.append({"field": field, "op": ">=", "value": from_date})
    if to_date:
        filters.append({"field": field, "op": "<=", "value": to_date})
    return filters


async def _call_api(payload: dict[str, Any]) -> dict[str, Any]:
    """Make a single POST to Colppy's API endpoint."""
    async with httpx.AsyncClient(timeout=COLPPY_TIMEOUT) as client:
        resp = await client.post(COLPPY_API_URL, json=payload)
        resp.raise_for_status()
        return resp.json()


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────


async def login() -> dict[str, Any]:
    """
    Authenticate with Colppy and obtain a session token (claveSesion).
    Both auth.password and parameters.password must be MD5 hashed.
    Session duration: 60 minutes, renewed on each use.

    Returns {"success": bool, "message": str, "data": {"claveSesion": str} | None}
    """
    try:
        creds = _get_credentials()
    except ValueError as e:
        return {"success": False, "message": str(e), "data": None}

    payload = {
        "auth": _auth_block(creds),
        "service": {
            "provision": "Usuario",
            "operacion": "iniciar_sesion",
        },
        "parameters": {
            "usuario": creds["COLPPY_USER"],
            "password": _md5(creds["COLPPY_PASSWORD"]),
        },
    }

    try:
        data = await _call_api(payload)
        ok, msg = _check_response(data)
        if not ok:
            return {"success": False, "message": msg, "data": None}

        clave_sesion = data["response"]["data"]["claveSesion"]
        return {
            "success": True,
            "message": "Sesión iniciada",
            "data": {"claveSesion": clave_sesion},
        }
    except httpx.HTTPStatusError as e:
        return {"success": False, "message": f"HTTP error: {e}", "data": None}
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}


async def _authenticated_call(
    clave_sesion: str,
    provision: str,
    operacion: str,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Generic authenticated call to Colppy API.
    Returns {"success": bool, "message": str, "data": list | dict | None}
    """
    creds = _get_credentials()
    params: dict[str, Any] = {
        "sesion": {
            "usuario": creds["COLPPY_USER"],
            "claveSesion": clave_sesion,
        },
    }
    if extra_params:
        params.update(extra_params)

    payload = {
        "auth": _auth_block(creds),
        "service": {
            "provision": provision,
            "operacion": operacion,
        },
        "parameters": params,
    }

    try:
        data = await _call_api(payload)
        ok, msg = _check_response(data)
        if not ok:
            return {"success": False, "message": msg, "data": None}
        return {
            "success": True,
            "message": "OK",
            "data": data["response"]["data"],
        }
    except httpx.HTTPStatusError as e:
        return {"success": False, "message": f"HTTP error: {e}", "data": None}
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}


async def _list_call(
    clave_sesion: str,
    provision: str,
    operacion: str,
    id_empresa: str,
    filters: list[dict[str, Any]] | None = None,
    order: dict[str, Any] | list[dict[str, Any]] | None = None,
    start: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """
    Single-page list call with proper required params per official docs.
    All listar_* operations require: idEmpresa, start, limit, filter, order.

    Returns {"success": bool, "message": str, "data": list | None}
    """
    if filters is None:
        filters = []
    if order is None:
        order = {"field": [], "order": ""}

    return await _authenticated_call(
        clave_sesion, provision, operacion,
        extra_params={
            "idEmpresa": id_empresa,
            "start": start,
            "limit": limit,
            "filter": filters,
            "order": order,
        },
    )


async def _list_all(
    clave_sesion: str,
    provision: str,
    operacion: str,
    id_empresa: str,
    filters: list[dict[str, Any]] | None = None,
    order: dict[str, Any] | list[dict[str, Any]] | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = 20,
) -> dict[str, Any]:
    """
    Auto-paginating list call. Fetches pages until len(results) < page_size.
    Returns {"success": bool, "message": str, "data": list}
    """
    all_items: list[Any] = []
    start = 0
    for _ in range(max_pages):
        result = await _list_call(
            clave_sesion, provision, operacion, id_empresa,
            filters=filters, order=order, start=start, limit=page_size,
        )
        if not result["success"]:
            if all_items:
                return {"success": True, "message": f"Partial: {result['message']}", "data": all_items}
            return result

        page = result["data"] or []
        if not isinstance(page, list):
            page = [page]
        all_items.extend(page)

        if len(page) < page_size:
            break
        start += page_size

    return {"success": True, "message": "OK", "data": all_items}


async def list_empresas(clave_sesion: str) -> dict[str, Any]:
    """List all companies the user has access to."""
    return await _authenticated_call(
        clave_sesion, "Empresa", "listar_empresa",
        extra_params={
            "start": 0,
            "limit": 50,
            "filter": [],
            "order": {"field": ["IdEmpresa"], "order": "asc"},
        },
    )


async def list_clientes(
    clave_sesion: str,
    id_empresa: str,
    only_active: bool = True,
) -> dict[str, Any]:
    """
    List clients for a company.
    Docs: order is mandatory. filter: [] if empty.
    """
    filters: list[dict[str, Any]] = []
    if only_active:
        filters.append({"field": "Activo", "op": "=", "value": "1"})
    return await _list_all(
        clave_sesion, "Cliente", "listar_cliente", id_empresa,
        filters=filters,
        order=[{"field": "RazonSocial", "order": "ASC"}],
    )


async def list_proveedores(
    clave_sesion: str,
    id_empresa: str,
    only_active: bool = True,
) -> dict[str, Any]:
    """
    List all suppliers for a company.
    Docs: order is mandatory (even if empty fields).
    """
    filters: list[dict[str, Any]] = []
    if only_active:
        filters.append({"field": "Activo", "op": "=", "value": "1"})
    return await _list_all(
        clave_sesion, "Proveedor", "listar_proveedor", id_empresa,
        filters=filters,
        order=[{"field": "NombreFantasia", "order": "ASC"}],
    )


async def list_comprobantes_compra(
    clave_sesion: str,
    id_empresa: str,
    from_date: str = "",
    to_date: str = "",
) -> dict[str, Any]:
    """
    List all purchase invoices (facturas de compra).
    Operation: 'listar_facturasCompra' (capital C — case sensitive!).
    Date filtering via filter array on 'fechaFactura', NOT fromDate/toDate.
    """
    filters = _build_date_filter(from_date, to_date, "fechaFactura")
    return await _list_all(
        clave_sesion, "FacturaCompra", "listar_facturasCompra", id_empresa,
        filters=filters,
        order={"field": ["idTipoComprobante", "idFactura"], "order": "asc"},
    )


async def list_comprobantes_venta(
    clave_sesion: str,
    id_empresa: str,
    from_date: str = "",
    to_date: str = "",
) -> dict[str, Any]:
    """
    List all sales invoices (facturas de venta).
    Operation: 'listar_facturasventa' (all lowercase — case sensitive!).
    Date filtering via filter array on 'fechaFactura'.
    Max limit per page: 5000 (per wiki docs).
    """
    filters = _build_date_filter(from_date, to_date, "fechaFactura")
    return await _list_all(
        clave_sesion, "FacturaVenta", "listar_facturasventa", id_empresa,
        filters=filters,
        order={"field": ["idTipoComprobante", "idFactura"], "order": "asc"},
    )


async def logout(clave_sesion: str) -> dict[str, Any]:
    """Close a Colppy session."""
    creds = _get_credentials()
    payload = {
        "auth": _auth_block(creds),
        "service": {
            "provision": "Usuario",
            "operacion": "cerrar_sesion",
        },
        "parameters": {
            "sesion": {
                "usuario": creds["COLPPY_USER"],
                "claveSesion": clave_sesion,
            },
        },
    }
    try:
        data = await _call_api(payload)
        ok, msg = _check_response(data)
        if not ok:
            return {"success": False, "message": msg, "data": None}
        return {"success": True, "message": "Sesión cerrada", "data": None}
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}
