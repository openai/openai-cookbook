"""
Colppy API router — endpoints to interact with Colppy's accounting API.

All endpoints follow the pattern:
  1. Login → get claveSesion
  2. Call the desired operation
  3. Logout (best-effort)
  4. Return {"success": bool, ...}

The session is short-lived (login/call/logout per request) to avoid stale tokens.
"""

from fastapi import APIRouter, Query

from backend.services import colppy_api

router = APIRouter()


@router.get("/health")
async def colppy_health():
    """Test Colppy API connectivity by logging in and out."""
    result = await colppy_api.login()
    if not result["success"]:
        return {
            "success": False,
            "error": f"Login failed: {result['message']}",
            "stage": "login",
        }

    clave = result["data"]["claveSesion"]

    # Verify session works by listing empresas
    empresas_result = await colppy_api.list_empresas(clave)
    await colppy_api.logout(clave)

    if not empresas_result["success"]:
        return {
            "success": False,
            "error": f"list_empresas failed: {empresas_result['message']}",
            "stage": "list_empresas",
        }

    empresas = empresas_result["data"] or []
    return {
        "success": True,
        "message": f"Conectado a Colppy. {len(empresas)} empresa(s) accesibles.",
        "empresas": [
            {
                "id": e.get("IdEmpresa"),
                "nombre": e.get("Nombre"),
                "razon_social": e.get("razonSocial"),
                "cuit": e.get("CUIT"),
                "activa": e.get("activa"),
            }
            for e in empresas
        ],
    }


@router.get("/empresas")
async def colppy_empresas():
    """List all companies the authenticated user can access."""
    result = await colppy_api.login()
    if not result["success"]:
        return {"success": False, "error": result["message"]}

    clave = result["data"]["claveSesion"]
    empresas_result = await colppy_api.list_empresas(clave)
    await colppy_api.logout(clave)
    return empresas_result


@router.get("/clientes")
async def colppy_clientes(
    id_empresa: str = Query(default=None, description="Company ID (defaults to COLPPY_ID_EMPRESA env)"),
):
    """List clients for a company."""
    import os
    id_empresa = id_empresa or os.getenv("COLPPY_ID_EMPRESA", "")
    if not id_empresa:
        return {"success": False, "error": "id_empresa is required"}

    result = await colppy_api.login()
    if not result["success"]:
        return {"success": False, "error": result["message"]}

    clave = result["data"]["claveSesion"]
    clientes_result = await colppy_api.list_clientes(clave, id_empresa)
    await colppy_api.logout(clave)

    items = clientes_result.get("data") or []
    return {
        "success": clientes_result["success"],
        "message": clientes_result.get("message", ""),
        "total": len(items) if isinstance(items, list) else 0,
        "data": items,
    }


@router.get("/proveedores")
async def colppy_proveedores(
    id_empresa: str = Query(default=None, description="Company ID"),
):
    """List suppliers for a company."""
    import os
    id_empresa = id_empresa or os.getenv("COLPPY_ID_EMPRESA", "")
    if not id_empresa:
        return {"success": False, "error": "id_empresa is required"}

    result = await colppy_api.login()
    if not result["success"]:
        return {"success": False, "error": result["message"]}

    clave = result["data"]["claveSesion"]
    proveedores_result = await colppy_api.list_proveedores(clave, id_empresa)
    await colppy_api.logout(clave)

    items = proveedores_result.get("data") or []
    return {
        "success": proveedores_result["success"],
        "message": proveedores_result.get("message", ""),
        "total": len(items) if isinstance(items, list) else 0,
        "data": items,
    }


@router.get("/comprobantes/compra")
async def colppy_comprobantes_compra(
    id_empresa: str = Query(default=None, description="Company ID"),
    from_date: str = Query(default="", description="Start date YYYY-MM-DD"),
    to_date: str = Query(default="", description="End date YYYY-MM-DD"),
):
    """List purchase invoices (facturas de compra)."""
    import os
    id_empresa = id_empresa or os.getenv("COLPPY_ID_EMPRESA", "")
    if not id_empresa:
        return {"success": False, "error": "id_empresa is required"}

    result = await colppy_api.login()
    if not result["success"]:
        return {"success": False, "error": result["message"]}

    clave = result["data"]["claveSesion"]
    comprobantes_result = await colppy_api.list_comprobantes_compra(
        clave, id_empresa, from_date, to_date,
    )
    await colppy_api.logout(clave)

    items = comprobantes_result.get("data") or []
    return {
        "success": comprobantes_result["success"],
        "message": comprobantes_result.get("message", ""),
        "total": len(items) if isinstance(items, list) else 0,
        "data": items,
    }


@router.get("/comprobantes/venta")
async def colppy_comprobantes_venta(
    id_empresa: str = Query(default=None, description="Company ID"),
    from_date: str = Query(default="", description="Start date YYYY-MM-DD"),
    to_date: str = Query(default="", description="End date YYYY-MM-DD"),
):
    """List sales invoices (facturas de venta)."""
    import os
    id_empresa = id_empresa or os.getenv("COLPPY_ID_EMPRESA", "")
    if not id_empresa:
        return {"success": False, "error": "id_empresa is required"}

    result = await colppy_api.login()
    if not result["success"]:
        return {"success": False, "error": result["message"]}

    clave = result["data"]["claveSesion"]
    comprobantes_result = await colppy_api.list_comprobantes_venta(
        clave, id_empresa, from_date, to_date,
    )
    await colppy_api.logout(clave)

    items = comprobantes_result.get("data") or []
    return {
        "success": comprobantes_result["success"],
        "message": comprobantes_result.get("message", ""),
        "total": len(items) if isinstance(items, list) else 0,
        "data": items,
    }
