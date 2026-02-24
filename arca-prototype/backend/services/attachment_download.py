"""
ARCA DFE Attachment Download.

Downloads PDF attachments from DFE notifications.

Strategy:
1. Login to DFE via Playwright, establish authenticated session
2. Fetch notification detail via REST API to get adjunto metadata (idArchivo, filename)
3. Download PDF via GET /api/v1/communications/{idComunicacion}/{idArchivo}
4. Save to disk and SQLite cache
"""
import asyncio
import base64
import json
import os
import urllib.parse
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

ARCA_LOGIN_URL = os.getenv("ARCA_LOGIN_URL", "https://auth.afip.gob.ar/contribuyente/")
TIMEOUT_MS = int(os.getenv("ARCA_TIMEOUT_MS", "45000"))
HEADLESS = os.getenv("ARCA_HEADLESS", "true").lower() == "true"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "attachments"


async def download_attachment(
    cuit: str,
    password: str,
    notification_id: int,
    id_archivo: int = 0,
    filename: str = "",
    cuit_representado: str = "",
) -> dict[str, Any]:
    """
    Download a PDF attachment from a DFE notification.

    Logs into DFE, fetches notification detail to discover attachment metadata,
    then downloads the PDF via the REST API.

    Args:
        cuit: 11-digit CUIT for ARCA login
        password: Clave Fiscal password
        notification_id: Communication ID
        id_archivo: File ID (optional — will be discovered from notification detail)
        filename: Output filename (optional — will use AFIP's filename)
        cuit_representado: CUIT of the entity that owns the notification (for DFE API query).
                           Falls back to cuit if not provided.

    Returns:
        {success, path, error, message}
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    # Use representado CUIT for API queries and cache, login CUIT for auth
    cuit_query = "".join(c for c in (cuit_representado or cuit) if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos", "path": None}

    auth_data: dict[str, Any] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()
        page.set_default_timeout(TIMEOUT_MS)

        async def capture_auth(resp):
            if "e-ventanilla/autorizacion" in resp.url:
                try:
                    auth_data["data"] = await resp.json()
                except Exception:
                    pass

        page.on("response", capture_auth)

        try:
            # Step 1: Login
            await page.goto(ARCA_LOGIN_URL, wait_until="networkidle")
            await asyncio.sleep(2)
            await page.locator('input[name="F1:username"]').fill(cuit_clean)
            await page.locator('input[name="F1:btnSiguiente"]').click()
            await asyncio.sleep(3)
            await page.locator('input[name="F1:password"]').fill(password)
            await page.locator('input[name="F1:btnIngresar"]').click()
            await asyncio.sleep(8)

            if "login" in page.url.lower() and "portal" not in page.url.lower():
                await browser.close()
                return {"success": False, "error": "Login fallido", "path": None}

            # Step 2: Navigate to DFE to capture auth token
            dfe_link = page.get_by_text("Domicilio Fiscal Electrónico", exact=False)
            await dfe_link.first.wait_for(state="visible", timeout=15000)
            await dfe_link.first.click()
            await asyncio.sleep(8)

            if "data" not in auth_data:
                await browser.close()
                return {"success": False, "error": "No se obtuvo autorización DFE", "path": None}

            # Step 3: Open DFE app to establish session
            token = auth_data["data"]["token"]
            sign = auth_data["data"]["sign"]
            dfe_url = (
                f"https://ve.cloud.afip.gob.ar/login"
                f"?token={urllib.parse.quote(token)}"
                f"&sign={urllib.parse.quote(sign)}"
            )
            await page.goto(dfe_url, wait_until="networkidle")
            await asyncio.sleep(4)

            try:
                btn = page.get_by_role("button", name="ENTENDIDO")
                await btn.wait_for(state="visible", timeout=5000)
                await btn.click()
                await asyncio.sleep(1)
            except Exception:
                pass

            # Step 4: Discover attachment metadata if id_archivo not provided
            if not id_archivo:
                detail_url = (
                    f"https://ve.cloud.afip.gob.ar/api/v1/communications/{notification_id}"
                    f"?id={notification_id}&cuit={cuit_query}"
                )
                detail_resp = await page.evaluate(
                    """async (url) => {
                        const r = await fetch(url);
                        return { status: r.status, body: await r.text() };
                    }""",
                    detail_url,
                )
                if detail_resp["status"] != 200:
                    await browser.close()
                    return {
                        "success": False,
                        "error": f"Detail API returned {detail_resp['status']}",
                        "path": None,
                    }

                detail_data = json.loads(detail_resp["body"])
                comm = detail_data.get("comunicacion", {})
                adjuntos = comm.get("adjuntos", [])

                if not adjuntos:
                    await browser.close()
                    return {
                        "success": False,
                        "error": "La notificación no tiene adjuntos",
                        "path": None,
                    }

                # Extract first adjunto metadata
                adj = adjuntos[0]
                inner = adj.get("adjunto", adj)
                id_archivo = inner.get("idArchivo") or inner.get("id", 0)
                if not filename:
                    filename = inner.get("filename") or inner.get("nombre") or f"attachment_{notification_id}.pdf"

            if not id_archivo:
                await browser.close()
                return {"success": False, "error": "No se encontró idArchivo", "path": None}

            if not filename:
                filename = f"attachment_{notification_id}.pdf"

            # Step 5: Download PDF via REST API
            # URL pattern: /api/v1/communications/{idComunicacion}/{idArchivo}
            download_url = f"https://ve.cloud.afip.gob.ar/api/v1/communications/{notification_id}/{id_archivo}"
            pdf_resp = await page.evaluate(
                """async (url) => {
                    const r = await fetch(url);
                    const ct = r.headers.get('content-type') || '';
                    if (r.ok) {
                        const buf = await r.arrayBuffer();
                        const bytes = new Uint8Array(buf);
                        let binary = '';
                        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
                        return { status: r.status, ct: ct, b64: btoa(binary), size: bytes.length };
                    }
                    const text = await r.text();
                    return { status: r.status, ct: ct, body: text.substring(0, 500), size: 0 };
                }""",
                download_url,
            )

            await browser.close()

            if not pdf_resp.get("b64") or pdf_resp.get("size", 0) < 100:
                return {
                    "success": False,
                    "error": f"Download failed: status={pdf_resp['status']} size={pdf_resp.get('size', 0)}",
                    "path": None,
                    "message": pdf_resp.get("body", ""),
                }

            # Save PDF
            pdf_bytes = base64.b64decode(pdf_resp["b64"])
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            out_path = OUTPUT_DIR / filename
            out_path.write_bytes(pdf_bytes)

            # Save to SQLite cache
            try:
                from backend.services.arca_db import save_pdf

                save_pdf(cuit_query, notification_id, pdf_bytes)
            except Exception:
                pass

            return {
                "success": True,
                "path": str(out_path),
                "error": None,
                "message": f"PDF descargado ({len(pdf_bytes)} bytes). Use GET /notificaciones/{notification_id}/pdf?cuit=... para recuperarlo.",
            }

        except Exception as e:
            try:
                await browser.close()
            except Exception:
                pass
            return {
                "success": False,
                "error": str(e),
                "path": None,
                "message": "Error durante la descarga.",
            }
