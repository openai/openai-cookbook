"""
ARCA API routes.
"""
import os

from fastapi import APIRouter, Query, UploadFile, File, Form
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from backend.services.arca_db import (
    delete_acknowledgment as db_delete_ack,
    delete_banco_transactions as db_delete_banco,
    delete_comprobantes as db_delete_comprobantes,
    delete_retenciones as db_delete_retenciones,
    get_acknowledgments as db_get_acks,
    get_banco_transactions as db_get_banco,
    get_comprobantes as db_get_comprobantes,
    get_last_fetched,
    get_notifications,
    get_pdf,
    get_representados as db_get_representados,
    get_retenciones as db_get_retenciones,
    save_acknowledgment as db_save_ack,
    save_banco_transactions as db_save_banco,
    save_comprobantes,
    save_pdf,
    save_retenciones as db_save_retenciones,
)
from backend.services.attachment_download import download_attachment
from backend.services.wsaa_client import get_credentials
from backend.services.arca_scraper import (
    login_and_scrape,
    open_domicilio_fiscal_electronico,
    read_all_notifications,
)
from backend.services.notifications_api import (
    get_notifications_with_content,
    get_representados as api_get_representados,
)
from backend.services.comprobantes_api import get_comprobantes_recibidos, get_comprobantes_emitidos
from backend.services.retenciones_api import download_retenciones
from backend.services.banco_galicia_scraper import get_savings_account_statements
from backend.services.reconciliacion_service import reconcile_retenciones
from backend.services.libro_iva_converter import (
    build_libro_iva_zip,
    comprobantes_to_libro_iva,
    csv_to_libro_iva_compras,
    csv_to_libro_iva_compras_full,
    csv_to_libro_iva_ventas,
    csv_to_libro_iva_ventas_full,
    get_csv_template,
)

router = APIRouter()


@router.get("/wsaa-test")
def wsaa_test():
    """
    Test WSAA certificate authentication. Returns success if ARCA_CERT_PATH and
    ARCA_KEY_PATH are configured and a valid token can be obtained.
    """
    try:
        creds = get_credentials(service="veconsumerws")
        return {
            "success": True,
            "message": "WSAA authentication OK. Token obtained.",
            "token_preview": creds["token"][:20] + "..." if creds.get("token") else None,
        }
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


class ArcaCredentials(BaseModel):
    """CUIT and Clave Fiscal for ARCA login."""

    cuit: str = Field(..., min_length=10, max_length=15, description="CUIT/CUIL (11 dígitos)")
    password: str = Field(..., min_length=1, description="Clave Fiscal")


class ArcaLoginResponse(BaseModel):
    """Response from ARCA login attempt."""

    success: bool
    message: str
    data: dict | None = None


@router.post("/login", response_model=ArcaLoginResponse)
async def arca_login(creds: ArcaCredentials) -> ArcaLoginResponse:
    """
    Attempt ARCA login with provided credentials.
    Returns success status and basic page data if login succeeds.
    """
    result = await login_and_scrape(creds.cuit, creds.password)
    return ArcaLoginResponse(**result)


@router.post("/domicilio-fiscal-electronico", response_model=ArcaLoginResponse)
async def arca_domicilio_fiscal_electronico(creds: ArcaCredentials) -> ArcaLoginResponse:
    """
    Log in and navigate to Domicilio Fiscal Electrónico.
    Returns notifications, comprobantes info, and page content.
    """
    result = await open_domicilio_fiscal_electronico(creds.cuit, creds.password)
    return ArcaLoginResponse(**result)


@router.post("/notificaciones", response_model=ArcaLoginResponse)
async def arca_notificaciones(creds: ArcaCredentials) -> ArcaLoginResponse:
    """
    Log in, access DFE app, and return full notification list with asunto, clasificación, recibido.
    """
    result = await read_all_notifications(creds.cuit, creds.password)
    return ArcaLoginResponse(**result)


@router.get("/representados")
async def representados_get(cuit: str | None = Query(None, description="CUIT del usuario. Si se omite, usa ARCA_CUIT de .env")):
    """
    Read representados from SQLite cache. No ARCA call.
    Use POST to fetch from ARCA. When cuit is omitted, uses ARCA_CUIT from env.
    """
    import os as _os
    cuit_clean = "".join(c for c in (cuit or _os.getenv("ARCA_CUIT", "")) if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos", "representados": []}
    items = db_get_representados(cuit_clean)
    return {"success": True, "representados": items, "source": "db"}


@router.get("/representados/refresh")
async def representados_refresh():
    """
    Fetch representados from ARCA using ARCA_CUIT and ARCA_PASSWORD from .env.
    No credentials needed in request.
    """
    import os as _os
    cuit = _os.getenv("ARCA_CUIT", "")
    password = _os.getenv("ARCA_PASSWORD", "")
    if not cuit or not password:
        return {"success": False, "error": "Configure ARCA_CUIT y ARCA_PASSWORD en .env", "representados": []}
    return await api_get_representados(cuit, password)


@router.post("/representados")
async def representados_post(creds: ArcaCredentials):
    """
    Fetch representados from ARCA DFE, save to SQLite, return list.
    """
    return await api_get_representados(creds.cuit, creds.password)


@router.get("/notificaciones-contenido")
async def notificaciones_contenido_get(cuit: str = Query(..., description="CUIT (11 dígitos)")):
    """
    Read notifications from local SQLite cache. No ARCA call.
    Use POST with credentials when you want to update from ARCA.
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos", "notifications": []}

    notifications, fetched_at = get_notifications(cuit_clean)
    if not notifications:
        return {
            "success": True,
            "cuit": cuit_clean,
            "total": 0,
            "notifications": [],
            "source": "db",
            "fetched_at": None,
            "message": "No hay datos en caché. Use POST con credenciales para actualizar desde ARCA.",
        }

    return {
        "success": True,
        "cuit": cuit_clean,
        "total": len(notifications),
        "notifications": notifications,
        "source": "db",
        "fetched_at": fetched_at,
    }


@router.get("/notificaciones-contenido/refresh")
async def notificaciones_contenido_refresh(
    cuit_representado: str = Query(..., description="CUIT del representado (11 dígitos)"),
):
    """
    Fetch notifications from ARCA for a representado using .env credentials.
    No credentials needed in request — uses ARCA_CUIT and ARCA_PASSWORD from .env.
    """
    import os as _os
    cuit = _os.getenv("ARCA_CUIT", "")
    password = _os.getenv("ARCA_PASSWORD", "")
    if not cuit or not password:
        return {"success": False, "error": "Configure ARCA_CUIT y ARCA_PASSWORD en .env", "notifications": []}
    cuit_clean = "".join(c for c in cuit_representado if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT representado debe tener 11 dígitos", "notifications": []}
    result = await get_notifications_with_content(cuit, password, cuit_representado=cuit_clean)
    if result.get("success") and result.get("fetched_at") is None:
        fetched = get_last_fetched(result.get("cuit", ""))
        if fetched:
            result["fetched_at"] = fetched
    return result


@router.get("/notificaciones/{notification_id}/pdf")
def notificacion_pdf(
    notification_id: int,
    cuit: str = Query(..., description="CUIT (11 dígitos)"),
):
    """
    Return PDF attachment for a notification from SQLite cache.
    Returns 404 if no PDF stored (e.g. notification has no attachment or not yet fetched).
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return Response(status_code=400, content="CUIT debe tener 11 dígitos")
    pdf_bytes = get_pdf(cuit_clean, notification_id)
    if not pdf_bytes:
        return Response(status_code=404, content="PDF no disponible en caché")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=notif-{notification_id}.pdf"},
    )


@router.get("/notificaciones/{notification_id}/pdf/download")
async def notificacion_pdf_download(
    notification_id: int,
    cuit: str = Query(..., description="CUIT (11 dígitos) — used for cache key and DFE query"),
):
    """
    Download PDF from ARCA DFE and cache it. Uses ARCA_CUIT/ARCA_PASSWORD from .env.
    Returns the PDF directly on success, or JSON error on failure.
    Slow (~30s) — involves Playwright login. Use GET /notificaciones/{id}/pdf for cache hits.
    """
    import os as _os
    login_cuit = _os.getenv("ARCA_CUIT", "")
    login_password = _os.getenv("ARCA_PASSWORD", "")
    if not login_cuit or not login_password:
        return {"success": False, "error": "Configure ARCA_CUIT y ARCA_PASSWORD en .env"}
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos"}

    # Check cache first
    cached = get_pdf(cuit_clean, notification_id)
    if cached:
        return Response(
            content=cached,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=notif-{notification_id}.pdf"},
        )

    # Download from ARCA — use login CUIT for auth, representado CUIT for DFE query
    result = await download_attachment(
        cuit=login_cuit,
        password=login_password,
        notification_id=notification_id,
        cuit_representado=cuit_clean,
    )
    if not result.get("success"):
        return result

    # Return the PDF from cache (download_attachment saves it)
    pdf_bytes = get_pdf(cuit_clean, notification_id)
    if not pdf_bytes:
        # Fallback: read from disk
        path = result.get("path")
        if path:
            from pathlib import Path as _P
            disk_bytes = _P(path).read_bytes()
            return Response(
                content=disk_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f"inline; filename=notif-{notification_id}.pdf"},
            )
        return {"success": False, "error": "PDF descargado pero no se pudo recuperar del caché"}

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=notif-{notification_id}.pdf"},
    )


class NotificacionesContenidoRequest(BaseModel):
    """Request for fetching notifications, optionally for a representado."""

    cuit: str = Field(..., min_length=10, max_length=15)
    password: str = Field(..., min_length=1)
    cuit_representado: str | None = Field(
        default=None,
        description="CUIT del representado (comunicaciones de mis representados). Si se omite, usa el CUIT del usuario.",
    )


@router.post("/notificaciones-contenido")
async def notificaciones_contenido_post(creds: NotificacionesContenidoRequest):
    """
    Fetch from ARCA, save to SQLite, and return JSON with all notifications.
    Use cuit_representado for "Comunicaciones de mis representados".
    """
    cuit_fetch = creds.cuit_representado or creds.cuit
    cuit_fetch_clean = "".join(c for c in cuit_fetch if c.isdigit())
    if len(cuit_fetch_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos", "notifications": []}
    result = await get_notifications_with_content(creds.cuit, creds.password, cuit_representado=cuit_fetch_clean)
    if result.get("success") and result.get("fetched_at") is None:
        fetched = get_last_fetched(result.get("cuit", ""))
        if fetched:
            result["fetched_at"] = fetched
    return result


class AttachmentDownloadRequest(BaseModel):
    """Request to download a notification attachment."""

    cuit: str = Field(..., min_length=10, max_length=15)
    password: str = Field(..., min_length=1)
    notification_id: int = Field(..., description="ID de la comunicación (ej. 582958952)")
    id_archivo: int = Field(
        default=0,
        description="ID del archivo adjunto. 0 = auto-discover from notification detail.",
    )
    filename: str = Field(
        default="",
        description="Nombre del archivo. Vacío = auto-discover from API.",
    )


@router.post("/attachments/upload")
async def upload_notification_attachment(
    cuit: str = Form(..., description="CUIT (11 dígitos)"),
    notification_id: int = Form(..., description="ID de la comunicación (ej. 582958952)"),
    file: UploadFile = File(..., description="Archivo PDF del adjunto"),
):
    """
    Upload a PDF attachment to store in SQLite. Use when you downloaded the PDF
    manually from DFE. The notification must already exist in cache (run POST
    notificaciones-contenido first). Then retrieve via GET /notificaciones/{id}/pdf?cuit=...
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos"}
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return {"success": False, "error": "Debe subir un archivo PDF"}
    try:
        pdf_bytes = await file.read()
        if len(pdf_bytes) < 100:
            return {"success": False, "error": "Archivo demasiado pequeño o vacío"}
        if save_pdf(cuit_clean, notification_id, pdf_bytes):
            return {
                "success": True,
                "message": f"PDF guardado para notificación {notification_id}. Recupere con GET /notificaciones/{notification_id}/pdf?cuit={cuit_clean}",
            }
        return {
            "success": False,
            "error": f"Notificación {notification_id} no encontrada en caché. Ejecute primero POST /notificaciones-contenido para cargar las notificaciones.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/attachments/download")
async def download_notification_attachment(req: AttachmentDownloadRequest):
    """
    Download a notification attachment (PDF) via DFE REST API.

    Flow: Login → DFE auth → GET /api/v1/communications/{id} to discover adjuntos →
    GET /api/v1/communications/{id}/{idArchivo} for PDF binary → save to disk and SQLite.

    id_archivo=0 triggers auto-discovery from notification detail. Pass a known ID if preferred.
    Prereq: notification must exist in cache (run POST notificaciones-contenido first).
    """
    return await download_attachment(
        cuit=req.cuit,
        password=req.password,
        notification_id=req.notification_id,
        id_archivo=req.id_archivo,
        filename=req.filename,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Comprobantes Recibidos
# ──────────────────────────────────────────────────────────────────────────────

class ComprobantesRequest(BaseModel):
    """Request for fetching comprobantes recibidos from ARCA."""

    cuit: str = Field(..., min_length=10, max_length=15, description="CUIT/CUIL (11 dígitos)")
    password: str = Field(..., min_length=1, description="Clave Fiscal")
    fecha_desde: str = Field(..., description="Fecha inicio DD/MM/YYYY")
    fecha_hasta: str = Field(..., description="Fecha fin DD/MM/YYYY")
    tipos_comprobante: str = Field(
        default="",
        description="Códigos de tipo comprobante separados por coma (vacío = todos). Ej: '1,6,11' para Facturas A/B/C.",
    )
    id_contribuyente: int = Field(
        default=1,
        description="Índice de persona/empresa a seleccionar (0-based). Default 1 = persona física.",
    )


@router.get("/comprobantes-recibidos")
async def comprobantes_get(
    cuit: str = Query(..., description="CUIT del representado (la entidad dueña de los comprobantes)"),
    fecha_desde: str | None = Query(default=None, description="Filtro fecha inicio ISO YYYY-MM-DD"),
    fecha_hasta: str | None = Query(default=None, description="Filtro fecha fin ISO YYYY-MM-DD"),
):
    """
    Read comprobantes recibidos from local SQLite cache. No ARCA call.
    The `cuit` param is the CUIT of the entity (representado) — e.g. 30712461221 for a company
    or 20268448536 for a personal CUIT.
    Use POST with credentials to fetch from ARCA.
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos", "comprobantes": []}

    comprobantes, fetched_at = db_get_comprobantes(cuit_clean, "R", fecha_desde, fecha_hasta)
    if not comprobantes:
        return {
            "success": True,
            "cuit_representado": cuit_clean,
            "total": 0,
            "comprobantes": [],
            "source": "db",
            "fetched_at": None,
            "message": "No hay datos en caché. Use POST con credenciales para actualizar desde ARCA.",
        }

    return {
        "success": True,
        "cuit_representado": cuit_clean,
        "total": len(comprobantes),
        "comprobantes": comprobantes,
        "source": "db",
        "fetched_at": fetched_at,
    }


@router.post("/comprobantes-recibidos")
async def comprobantes_post(req: ComprobantesRequest):
    """
    Fetch comprobantes recibidos from ARCA Mis Comprobantes, save to SQLite, return JSON.

    This logs into ARCA, navigates to Mis Comprobantes > Comprobantes Recibidos,
    and fetches all comprobantes in the given date range (DD/MM/YYYY format).

    The result is cached in SQLite — subsequent GET requests read from cache.
    """
    result = await get_comprobantes_recibidos(
        cuit=req.cuit,
        password=req.password,
        fecha_desde=req.fecha_desde,
        fecha_hasta=req.fecha_hasta,
        tipos_comprobante=req.tipos_comprobante,
        id_contribuyente=req.id_contribuyente,
    )

    # Save to SQLite on success — key by cuit_representado (the entity that owns
    # these comprobantes), which may differ from the login CUIT when representing
    # a company (e.g. ALL ONLINE SOLUTIONS).
    if result.get("success") and result.get("comprobantes"):
        cuit_clean = "".join(c for c in req.cuit if c.isdigit())
        cuit_repr = result.get("cuit_representado") or cuit_clean
        save_comprobantes(cuit_repr, result["comprobantes"], direccion="R")
        result["source"] = "arca"

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Comprobantes Emitidos
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/comprobantes-emitidos")
async def comprobantes_emitidos_get(
    cuit: str = Query(..., description="CUIT del representado (la entidad dueña de los comprobantes)"),
    fecha_desde: str | None = Query(default=None, description="Filtro fecha inicio ISO YYYY-MM-DD"),
    fecha_hasta: str | None = Query(default=None, description="Filtro fecha fin ISO YYYY-MM-DD"),
):
    """
    Read comprobantes emitidos from local SQLite cache. No ARCA call.
    The `cuit` param is the CUIT of the entity (representado) — e.g. 30712461221 for a company
    or 20268448536 for a personal CUIT.
    Use POST with credentials to fetch from ARCA.
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos", "comprobantes": []}

    comprobantes, fetched_at = db_get_comprobantes(cuit_clean, "E", fecha_desde, fecha_hasta)
    if not comprobantes:
        return {
            "success": True,
            "cuit_representado": cuit_clean,
            "total": 0,
            "comprobantes": [],
            "source": "db",
            "fetched_at": None,
            "message": "No hay datos en caché. Use POST con credenciales para actualizar desde ARCA.",
        }

    return {
        "success": True,
        "cuit_representado": cuit_clean,
        "total": len(comprobantes),
        "comprobantes": comprobantes,
        "source": "db",
        "fetched_at": fetched_at,
    }


@router.post("/comprobantes-emitidos")
async def comprobantes_emitidos_post(req: ComprobantesRequest):
    """
    Fetch comprobantes emitidos from ARCA Mis Comprobantes, save to SQLite, return JSON.

    This logs into ARCA, navigates to Mis Comprobantes > Comprobantes Emitidos,
    and fetches all comprobantes in the given date range (DD/MM/YYYY format).

    The result is cached in SQLite — subsequent GET requests read from cache.
    """
    result = await get_comprobantes_emitidos(
        cuit=req.cuit,
        password=req.password,
        fecha_desde=req.fecha_desde,
        fecha_hasta=req.fecha_hasta,
        tipos_comprobante=req.tipos_comprobante,
        id_contribuyente=req.id_contribuyente,
    )

    # Save to SQLite on success — key by cuit_representado (the actual entity)
    if result.get("success") and result.get("comprobantes"):
        cuit_clean = "".join(c for c in req.cuit if c.isdigit())
        cuit_repr = result.get("cuit_representado") or cuit_clean
        save_comprobantes(cuit_repr, result["comprobantes"], direccion="E")
        result["source"] = "arca"

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Mis Retenciones — Download retenciones y percepciones (Exportar para Aplicativo)
# ──────────────────────────────────────────────────────────────────────────────

class RetencionesRequest(BaseModel):
    """Request for downloading retenciones from ARCA Mis Retenciones."""

    cuit: str | None = Field(
        default=None, description="CUIT para login. Si se omite, usa ARCA_CUIT de .env",
    )
    password: str | None = Field(
        default=None, description="Clave Fiscal. Si se omite, usa ARCA_PASSWORD de .env",
    )
    cuit_representado: str | None = Field(
        default=None,
        description="CUIT del representado a consultar. Si se omite, usa el CUIT de login.",
    )
    fecha_desde: str = Field(..., description="Fecha inicio DD/MM/YYYY")
    fecha_hasta: str = Field(..., description="Fecha fin DD/MM/YYYY")
    id_contribuyente: int = Field(
        default=0,
        description="Índice de persona/empresa a seleccionar (0-based). Default 0 = primera.",
    )
    impuesto: str = Field(
        default="767",
        description="Código de impuesto: 767 (SICORE Ret y Perc), 216 (IVA), 217 (Ganancias), 219 (Bs Personales)",
    )
    tipo_operacion: str = Field(
        default="retencion",
        description="Tipo de operación: 'retencion' o 'percepcion'",
    )


@router.get("/retenciones")
async def retenciones_get(
    cuit: str = Query(..., description="CUIT del representado"),
    fecha_desde: str | None = Query(default=None, description="Filtro fecha inicio ISO YYYY-MM-DD"),
    fecha_hasta: str | None = Query(default=None, description="Filtro fecha fin ISO YYYY-MM-DD"),
):
    """
    Read retenciones from local SQLite cache. No ARCA call.
    Use POST /retenciones/download to fetch from ARCA.
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos", "retenciones": []}
    retenciones, fetched_at = db_get_retenciones(cuit_clean, fecha_desde, fecha_hasta)
    if not retenciones:
        return {
            "success": True,
            "cuit_representado": cuit_clean,
            "total": 0,
            "retenciones": [],
            "source": "db",
            "fetched_at": None,
            "message": "No hay retenciones en caché. Use el botón Descargar para obtener datos de ARCA.",
        }
    return {
        "success": True,
        "cuit_representado": cuit_clean,
        "total": len(retenciones),
        "retenciones": retenciones,
        "source": "db",
        "fetched_at": fetched_at,
    }


@router.post("/retenciones/download")
async def retenciones_download(req: RetencionesRequest):
    """
    Download retenciones y percepciones from ARCA Mis Retenciones (Exportar para Aplicativo).

    Logs into ARCA, navigates to Mis Retenciones > Mis Retenciones Impositivas,
    runs a query for the date range, and triggers the CSV export.
    Saves to SQLite cache + data/ files. Returns the data and file path.

    Credentials default to .env (ARCA_CUIT, ARCA_PASSWORD).
    Use cuit_representado to query for a specific representado.
    """
    cuit = (req.cuit or os.getenv("ARCA_CUIT", "")).strip()
    password = (req.password or os.getenv("ARCA_PASSWORD", "")).strip()
    if not cuit or not password:
        return {"success": False, "error": "Configure ARCA_CUIT y ARCA_PASSWORD en .env"}
    result = await download_retenciones(
        cuit=cuit,
        password=password,
        fecha_desde=req.fecha_desde,
        fecha_hasta=req.fecha_hasta,
        id_contribuyente=req.id_contribuyente,
        impuesto=req.impuesto,
        tipo_operacion=req.tipo_operacion,
    )
    # Save to SQLite on success
    if result.get("success") and result.get("retenciones"):
        cuit_repr = req.cuit_representado or cuit
        cuit_repr_clean = "".join(c for c in cuit_repr if c.isdigit())
        db_save_retenciones(cuit_repr_clean, result["retenciones"])
        result["source"] = "arca"
        result["saved_to_db"] = len(result["retenciones"])
    return result


@router.delete("/retenciones")
async def retenciones_delete(
    cuit: str = Query(..., description="CUIT del representado"),
):
    """
    Delete all cached retenciones for a representado.
    Use before a full refresh to clear stale data.
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos"}
    count = db_delete_retenciones(cuit_clean)
    return {"success": True, "deleted": count, "cuit": cuit_clean}


@router.get("/retenciones/file/{filename}")
async def retenciones_file_download(filename: str):
    """
    Serve a downloaded retenciones CSV file.
    Only allows filenames matching retenciones_*.csv from the data directory.
    """
    import re as _re
    from pathlib import Path as _Path

    if not _re.match(r"^retenciones_[a-zA-Z0-9_]+\.csv$", filename):
        return Response(status_code=400, content="Invalid filename")
    data_dir = _Path(__file__).resolve().parents[2] / "data"
    file_path = data_dir / filename
    if not file_path.exists():
        return Response(status_code=404, content="File not found")
    content = file_path.read_bytes()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/retenciones/reconcile")
async def retenciones_reconcile(
    cuit: str = Query(..., description="CUIT del representado"),
    fecha_desde: str | None = Query(default=None, description="Fecha inicio ISO YYYY-MM-DD"),
    fecha_hasta: str | None = Query(default=None, description="Fecha fin ISO YYYY-MM-DD"),
):
    """
    Reconcile retenciones against comprobantes recibidos. Both from SQLite cache.
    Cache-only — no ARCA calls. Fast.
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos"}
    retenciones, _ = db_get_retenciones(cuit_clean, fecha_desde, fecha_hasta)
    comprobantes, _ = db_get_comprobantes(cuit_clean, "R", fecha_desde, fecha_hasta)
    return reconcile_retenciones(retenciones, comprobantes, fecha_desde, fecha_hasta)


@router.get("/retenciones/download")
async def retenciones_download_get(
    fecha_desde: str = Query(..., description="Fecha inicio DD/MM/YYYY"),
    fecha_hasta: str = Query(..., description="Fecha fin DD/MM/YYYY"),
    cuit: str | None = Query(default=None, description="CUIT login (default: .env)"),
    password: str | None = Query(default=None, description="Clave Fiscal (default: .env)"),
    id_contribuyente: int = Query(0, description="Índice persona (0-based)"),
    impuesto: str = Query("767", description="Código impuesto (767=SICORE, 216=IVA, 217=Ganancias)"),
    tipo_operacion: str = Query("retencion", description="'retencion' o 'percepcion'"),
):
    """
    Same as POST /retenciones/download but via GET (for quick testing).
    Credentials default to .env (ARCA_CUIT, ARCA_PASSWORD).
    """
    cuit_val = (cuit or os.getenv("ARCA_CUIT", "")).strip()
    password_val = (password or os.getenv("ARCA_PASSWORD", "")).strip()
    if not cuit_val or not password_val:
        return {"success": False, "error": "Configure ARCA_CUIT y ARCA_PASSWORD en .env"}
    result = await download_retenciones(
        cuit=cuit_val,
        password=password_val,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        id_contribuyente=id_contribuyente,
        impuesto=impuesto,
        tipo_operacion=tipo_operacion,
    )
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Libro IVA Digital — CSV to AFIP format
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/libro-iva/template")
async def libro_iva_template(
    tipo: str = Query("ventas", description="ventas | compras"),
):
    """
    Return CSV template for Libro IVA import.
    User fills the CSV and uploads via POST /libro-iva/convert.
    """
    template = get_csv_template(tipo)
    return Response(
        content=template.encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="libro_iva_{tipo}_template.csv"'},
    )


@router.get("/libro-iva/generate")
async def libro_iva_generate(
    cuit: str = Query(..., description="CUIT del representado (entidad dueña de los comprobantes)"),
    fecha_desde: str = Query(..., description="Fecha inicio YYYY-MM-DD"),
    fecha_hasta: str = Query(..., description="Fecha fin YYYY-MM-DD"),
    tipo: str = Query("ventas", description="ventas | compras"),
):
    """
    Generate Libro IVA file from Mis Comprobantes (SQLite cache).
    ventas = emitidos, compras = recibidos.
    Returns AFIP-format file for import. Requires data in cache (run POST comprobantes-recibidos/emitidos first).
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos"}
    direccion = "E" if tipo == "ventas" else "R"
    comprobantes, _ = db_get_comprobantes(cuit_clean, direccion, fecha_desde, fecha_hasta)
    if not comprobantes:
        return {
            "success": False,
            "error": f"No hay comprobantes en caché para {cuit_clean} ({tipo}). Ejecute primero POST /comprobantes-{tipo} con credenciales.",
            "cuit": cuit_clean,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
        }
    cabeceras, alicuotas = comprobantes_to_libro_iva(comprobantes, tipo)
    zip_bytes = build_libro_iva_zip(cabeceras, alicuotas, tipo, fecha_desde, fecha_hasta)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="libro_iva_{tipo}_{fecha_desde}_{fecha_hasta}.zip"',
            "X-Comprobantes-Count": str(len(cabeceras)),
        },
    )


@router.get("/libro-iva/reconcile-data")
async def libro_iva_reconcile_data(
    cuit: str = Query(..., description="CUIT del representado"),
    fecha_desde: str = Query(..., description="Fecha inicio YYYY-MM-DD"),
    fecha_hasta: str = Query(..., description="Fecha fin YYYY-MM-DD"),
    tipo: str = Query("ventas", description="ventas | compras"),
):
    """
    Return comprobantes from Mis Comprobantes with IVA breakdown for reconciliation.
    Lets the user verify that nothing is missing before generating Libro IVA.
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos"}
    direccion = "E" if tipo == "ventas" else "R"
    comprobantes, fetched_at = db_get_comprobantes(cuit_clean, direccion, fecha_desde, fecha_hasta)
    enriched = []
    total_iva = 0.0
    total_neto = 0.0
    for c in comprobantes:
        imp_total = float(c.get("importe_total") or 0)
        imp_neto = imp_total / 1.21
        imp_iva = imp_total * 0.21 / 1.21
        total_neto += imp_neto
        total_iva += imp_iva
        enriched.append({
            **c,
            "importe_neto_calc": round(imp_neto, 2),
            "importe_iva_calc": round(imp_iva, 2),
        })
    return {
        "success": True,
        "cuit": cuit_clean,
        "tipo": tipo,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "comprobantes": enriched,
        "total_comprobantes": len(enriched),
        "total_neto": round(total_neto, 2),
        "total_iva": round(total_iva, 2),
        "fetched_at": fetched_at,
    }


@router.post("/libro-iva/convert")
async def libro_iva_convert(
    file: UploadFile = File(..., description="CSV con columnas: fecha, tipo_comp, punto_venta, numero_desde, numero_hasta, cuit_contraparte, denominacion, importe_total"),
    tipo: str = Form("ventas", description="ventas | compras"),
):
    """
    Convert CSV to AFIP Libro IVA Digital format.
    Returns ZIP with cabecera + alícuotas files for AFIP import.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return {"success": False, "error": "Debe subir un archivo CSV"}
    try:
        content = await file.read()
        if tipo == "compras":
            cabeceras, alicuotas, errors = csv_to_libro_iva_compras_full(content)
        else:
            cabeceras, alicuotas, errors = csv_to_libro_iva_ventas_full(content)
        if not cabeceras and errors:
            return {
                "success": False,
                "error": "No se pudieron procesar filas",
                "errors": errors[:20],
            }
        zip_bytes = build_libro_iva_zip(cabeceras, alicuotas, tipo, "", "")
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="libro_iva_{tipo}_afip.zip"',
                "X-Converted-Rows": str(len(cabeceras)),
                "X-Conversion-Errors": str(len(errors)),
            },
        )
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/libro-iva/convert-preview")
async def libro_iva_convert_preview(
    file: UploadFile = File(..., description="CSV para previsualizar conversión"),
    tipo: str = Form("ventas", description="ventas | compras"),
):
    """
    Convert CSV and return JSON preview (no file download).
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return {"success": False, "error": "Debe subir un archivo CSV"}
    try:
        content = await file.read()
        if tipo == "compras":
            cabeceras, alicuotas, errors = csv_to_libro_iva_compras_full(content)
        else:
            cabeceras, alicuotas, errors = csv_to_libro_iva_ventas_full(content)
        return {
            "success": True,
            "converted_rows": len(cabeceras),
            "errors": errors,
            "preview_cabecera": cabeceras[:5] if cabeceras else [],
            "preview_alicuotas": alicuotas[:5] if alicuotas else [],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# Banco Galicia — Bank transactions
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/banco/transactions")
async def banco_transactions_get(
    account: str | None = Query(default=None, description="Account filter (e.g. 'CA$')"),
    fecha_desde: str | None = Query(default=None, description="Filtro fecha desde DD/MM/YYYY"),
    fecha_hasta: str | None = Query(default=None, description="Filtro fecha hasta DD/MM/YYYY"),
):
    """
    Read bank transactions from SQLite cache. No bank call.
    Use POST /banco/refresh to fetch fresh data from Banco Galicia.
    """
    transactions, fetched_at = db_get_banco(account, fecha_desde, fecha_hasta)
    if not transactions:
        return {
            "success": True,
            "total": 0,
            "transactions": [],
            "source": "db",
            "fetched_at": None,
            "message": "No hay transacciones bancarias en caché. Use Descargar para obtener datos.",
        }

    # Compute summary
    ingresos = sum(t["amount"] for t in transactions if t["amount"] > 0)
    egresos = sum(t["amount"] for t in transactions if t["amount"] < 0)
    return {
        "success": True,
        "total": len(transactions),
        "transactions": transactions,
        "source": "db",
        "fetched_at": fetched_at,
        "summary": {
            "ingresos": round(ingresos, 2),
            "egresos": round(egresos, 2),
            "neto": round(ingresos + egresos, 2),
        },
    }


@router.post("/banco/refresh")
async def banco_refresh(
    account: str = Query(default="CA$", description="Account fragment to match (default: 'CA$' = Caja de Ahorro Pesos)"),
):
    """
    Fetch bank transactions from Banco Galicia via Playwright.
    Requires GALICIA_DNI, GALICIA_USER, GALICIA_PASS in .env.
    Saves results to SQLite cache automatically.
    """
    try:
        result = await get_savings_account_statements(
            account_fragment=account,
            export_csv=True,
        )
    except Exception as e:
        return {"success": False, "error": str(e)}

    if not result.get("success"):
        return result

    # Save transactions to SQLite (replace cache for this account to avoid stale data)
    data = result.get("data", {})
    raw_transactions = data.get("transactions", [])
    if raw_transactions:
        db_delete_banco(account)  # Remove old cached data before insert
        # Convert from BankTransaction dataclass dicts to save format
        to_save = []
        for t in raw_transactions:
            if isinstance(t, dict):
                to_save.append(t)
            else:
                # dataclass object
                to_save.append({
                    "date": t.date,
                    "description": t.description,
                    "amount": t.amount,
                    "balance": getattr(t, "balance", None),
                    "reference": getattr(t, "reference", None),
                })
        inserted = db_save_banco(account, to_save)
        result["saved_to_db"] = inserted
        result["source"] = "banco_galicia"

    return result


@router.delete("/banco/transactions")
async def banco_transactions_delete(
    account: str | None = Query(default=None, description="Account to clear. None = clear all."),
):
    """Delete cached bank transactions."""
    count = db_delete_banco(account)
    return {"success": True, "deleted": count}


# ──────────────────────────────────────────────────────────────────────────────
# Cache management
# ──────────────────────────────────────────────────────────────────────────────


@router.delete("/comprobantes/cache")
async def clear_comprobantes_cache(
    cuit: str = Query(description="CUIT del representado"),
    direccion: str = Query(default=None, description="R=recibidos, E=emitidos (omit for both)"),
    fecha_desde: str = Query(default=None, description="Start date YYYY-MM-DD"),
    fecha_hasta: str = Query(default=None, description="End date YYYY-MM-DD"),
):
    """Delete cached ARCA comprobantes so they can be re-fetched with corrected parsing."""
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    deleted = db_delete_comprobantes(cuit_clean, direccion, fecha_desde, fecha_hasta)
    return {"success": True, "deleted": deleted}


# ──────────────────────────────────────────────────────────────────────────────
# Reconciliation: ARCA Emitidos ↔ Colppy Ventas
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/reconcile/emitidos")
async def reconcile_emitidos(
    cuit: str = Query(description="CUIT del representado (e.g. 30712461221)"),
    fecha_desde: str = Query(default="2026-01-01", description="Start date YYYY-MM-DD"),
    fecha_hasta: str = Query(default="2026-01-31", description="End date YYYY-MM-DD"),
    id_empresa: str = Query(default=None, description="Colppy empresa ID (defaults to env)"),
):
    """
    Cross-reference ARCA comprobantes emitidos against Colppy facturas de venta.
    ARCA data comes from local SQLite cache; Colppy data is fetched live from API.
    """
    from backend.services.reconciliacion_emitidos import reconcile_emitidos as do_reconcile

    cuit_clean = "".join(c for c in cuit if c.isdigit())
    empresa = id_empresa or os.getenv("COLPPY_ID_EMPRESA", "")
    if not empresa:
        return {"success": False, "message": "id_empresa is required (set COLPPY_ID_EMPRESA env)"}

    return await do_reconcile(cuit_clean, empresa, fecha_desde, fecha_hasta)


@router.get("/reconcile/emitidos/stream")
async def reconcile_emitidos_stream(
    cuit: str = Query(description="CUIT del representado"),
    fecha_desde: str = Query(default="2026-01-01"),
    fecha_hasta: str = Query(default="2026-01-31"),
    id_empresa: str = Query(default=None),
):
    """SSE stream version of reconcile_emitidos with real-time progress."""
    from backend.services.reconciliacion_emitidos import reconcile_emitidos_stream as do_stream

    cuit_clean = "".join(c for c in cuit if c.isdigit())
    empresa = id_empresa or os.getenv("COLPPY_ID_EMPRESA", "")
    if not empresa:
        import json
        async def _err():
            yield f'data: {json.dumps({"type": "error", "message": "id_empresa is required"})}\n\n'
        return StreamingResponse(_err(), media_type="text/event-stream")

    return StreamingResponse(
        do_stream(cuit_clean, empresa, fecha_desde, fecha_hasta),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ──────────────────────────────────────────────────────────────────────────────
# Reconciliation: Recibidos (ARCA comprobantes recibidos ↔ Colppy compras)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/reconcile/recibidos/stream")
async def reconcile_recibidos_stream(
    cuit: str = Query(description="CUIT del representado"),
    fecha_desde: str = Query(default="2026-01-01"),
    fecha_hasta: str = Query(default="2026-01-31"),
    id_empresa: str = Query(default=None),
):
    """SSE stream: reconcile ARCA comprobantes recibidos vs Colppy facturas de compra."""
    from backend.services.reconciliacion_recibidos import reconcile_recibidos_stream as do_stream_recibidos

    cuit_clean = "".join(c for c in cuit if c.isdigit())
    empresa = id_empresa or os.getenv("COLPPY_ID_EMPRESA", "")
    if not empresa:
        import json as _json
        async def _err():
            yield f'data: {_json.dumps({"type": "error", "message": "id_empresa is required"})}\n\n'
        return StreamingResponse(_err(), media_type="text/event-stream")

    return StreamingResponse(
        do_stream_recibidos(cuit_clean, empresa, fecha_desde, fecha_hasta),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ──────────────────────────────────────────────────────────────────────────────
# Reconciliation: Discrepancy Acknowledgments
# ──────────────────────────────────────────────────────────────────────────────


class AcknowledgmentCreate(BaseModel):
    discrepancy_key: str
    status: str
    category: str = "revisado"
    reason: str = ""
    acknowledged_by: str = ""
    context_json: dict | None = None


class ReconcileSearchRequest(BaseModel):
    query: str
    cuit: str
    fecha_desde: str
    fecha_hasta: str
    scope: str = "discrepancies"
    conversation: list[dict] = []
    discrepancies: list[dict] = []
    matched_pairs: list[dict] = []


@router.get("/reconcile/acknowledgments")
def list_acknowledgments(
    status: str = Query(default=None, description="Filter by discrepancy status"),
):
    """List all reconciliation acknowledgments, optionally filtered by status."""
    acks = db_get_acks(status_filter=status)
    return {"success": True, "acknowledgments": acks, "total": len(acks)}


@router.post("/reconcile/acknowledgments")
def create_acknowledgment(body: AcknowledgmentCreate):
    """Create or update an acknowledgment for a discrepancy."""
    import json

    context_str = json.dumps(body.context_json) if body.context_json else None
    row_id = db_save_ack(
        discrepancy_key=body.discrepancy_key,
        status=body.status,
        category=body.category,
        reason=body.reason,
        acknowledged_by=body.acknowledged_by,
        context_json=context_str,
    )
    return {"success": True, "id": row_id, "discrepancy_key": body.discrepancy_key}


@router.delete("/reconcile/acknowledgments/{discrepancy_key:path}")
def remove_acknowledgment(discrepancy_key: str):
    """Remove an acknowledgment (un-acknowledge a discrepancy)."""
    deleted = db_delete_ack(discrepancy_key)
    return {"success": True, "deleted": deleted}


@router.post("/reconcile/search")
async def reconcile_search(body: ReconcileSearchRequest):
    """Stream LLM-powered search over reconciliation data."""
    from backend.services.reconciliation_search import search_invoices_stream

    return StreamingResponse(
        search_invoices_stream(
            query=body.query,
            cuit=body.cuit,
            fecha_desde=body.fecha_desde,
            fecha_hasta=body.fecha_hasta,
            scope=body.scope,
            conversation=body.conversation,
            discrepancies=body.discrepancies,
            matched_pairs=body.matched_pairs,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
