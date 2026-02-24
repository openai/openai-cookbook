"""
ARCA DFE Notifications API — uses the internal REST API for clean JSON extraction.

Flow:
  1. Login to ARCA portal via Playwright (CUIT + Clave Fiscal)
  2. Navigate to DFE to capture auth token/sign
  3. Open DFE app (ve.cloud.afip.gob.ar) — session cookies set
  4. Call /api/v1/communications to get notification list
  5. Call /api/v1/communications/{id} for each to get full content
  6. Return structured JSON
"""
import asyncio
import base64
import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import Any

from playwright.async_api import async_playwright

ARCA_LOGIN_URL = os.getenv("ARCA_LOGIN_URL", "https://auth.afip.gob.ar/contribuyente/")
TIMEOUT_MS = int(os.getenv("ARCA_TIMEOUT_MS", "45000"))
HEADLESS = os.getenv("ARCA_HEADLESS", "true").lower() == "true"
MAX_DETAIL_FETCH = int(os.getenv("ARCA_MAX_DETAIL_FETCH", "30"))


async def get_notifications_with_content(
    cuit: str, password: str, cuit_representado: str | None = None
) -> dict[str, Any]:
    """
    Returns structured JSON with all DFE notifications including full message content.
    Use cuit_representado for "Comunicaciones de mis representados" (fetch for a specific CUIT).
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    cuit_for_comms = (
        "".join(c for c in cuit_representado if c.isdigit()) if cuit_representado else cuit_clean
    )
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos", "notifications": []}

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
            # === STEP 1: Login to ARCA ===
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
                return {"success": False, "error": "Login fallido. Verifique CUIT y Clave Fiscal.", "notifications": []}

            # === STEP 2: Navigate to DFE to trigger auth token ===
            dfe_link = page.get_by_text("Domicilio Fiscal Electrónico", exact=False)
            await dfe_link.first.wait_for(state="visible", timeout=15000)
            await dfe_link.first.click()
            await asyncio.sleep(8)

            if "data" not in auth_data:
                await browser.close()
                return {"success": False, "error": "No se obtuvo autorización para DFE", "notifications": []}

            # === STEP 3: Open DFE app to establish session cookies ===
            token = auth_data["data"]["token"]
            sign = auth_data["data"]["sign"]
            dfe_url = (
                f"https://ve.cloud.afip.gob.ar/login"
                f"?token={urllib.parse.quote(token)}"
                f"&sign={urllib.parse.quote(sign)}"
            )
            await page.goto(dfe_url, wait_until="networkidle")
            await asyncio.sleep(4)

            # Close the info modal if it appears
            try:
                btn = page.get_by_role("button", name="ENTENDIDO")
                await btn.wait_for(state="visible", timeout=5000)
                await btn.click()
                await asyncio.sleep(1)
            except Exception:
                pass

            # === STEP 4: Call the communications list API ===
            today = datetime.now()
            since = (today - timedelta(days=365)).strftime("%Y-%m-%d")
            to = today.strftime("%Y-%m-%d")

            list_url = (
                f"https://ve.cloud.afip.gob.ar/api/v1/communications"
                f"?cuit={cuit_for_comms}"
                f"&fechaPublicacionSince={since}"
                f"&fechaPublicacionTo={to}"
            )

            list_resp = await page.evaluate(
                """async (url) => {
                    const r = await fetch(url);
                    return { status: r.status, body: await r.text() };
                }""",
                list_url,
            )

            if list_resp["status"] != 200:
                await browser.close()
                return {
                    "success": False,
                    "error": f"API communications list returned {list_resp['status']}",
                    "notifications": [],
                }

            list_data = json.loads(list_resp["body"])
            comunicaciones = list_data.get("comunicaciones", [])

            # === STEP 5: Fetch full content for each notification ===
            notifications = []
            for i, comm in enumerate(comunicaciones):
                nid = comm["idComunicacion"]
                notif: dict[str, Any] = {
                    "id": nid,
                    "organismo": comm.get("organismoDesc", ""),
                    "fecha_publicacion": _epoch_ms_to_iso(comm.get("fechaPublicacion")),
                    "fecha_vencimiento": _epoch_ms_to_iso(comm.get("fechaVencimiento")),
                    "fecha_notificacion": _epoch_ms_to_iso(comm.get("fechaNotificacion")),
                    "sistema": comm.get("sistemaPublicador"),
                    "estado": comm.get("estado"),
                    "prioridad": comm.get("prioridad"),
                    "tiene_adjunto": comm.get("tieneAdjunto", False),
                    "oficio": comm.get("oficio", False),
                    "tipo": comm.get("tipo"),
                    "mensaje_preview": comm.get("mensaje", ""),
                    "mensaje_completo": "",
                    "clasificacion": _classify(comm.get("tipo"), comm.get("prioridad")),
                }

                # Fetch full content via detail API
                if i < MAX_DETAIL_FETCH:
                    detail_url = (
                        f"https://ve.cloud.afip.gob.ar/api/v1/communications/{nid}"
                        f"?id={nid}&cuit={cuit_for_comms}"
                    )
                    try:
                        detail_resp = await page.evaluate(
                            """async (url) => {
                                const r = await fetch(url);
                                return { status: r.status, body: await r.text() };
                            }""",
                            detail_url,
                        )
                        if detail_resp["status"] == 200:
                            detail_data = json.loads(detail_resp["body"])
                            comm_detail = detail_data.get("comunicacion", {})
                            notif["mensaje_completo"] = comm_detail.get("mensaje", "")
                            if comm_detail.get("sistemaPublicadorDesc"):
                                notif["sistema_desc"] = comm_detail["sistemaPublicadorDesc"]
                            if comm_detail.get("estadoDesc"):
                                notif["estado_desc"] = comm_detail["estadoDesc"]
                            # Extract first PDF attachment if present
                            pdf_bytes = _extract_pdf_from_detail(comm_detail)
                            if pdf_bytes:
                                notif["pdf_content"] = pdf_bytes
                    except Exception:
                        pass  # Keep the preview if detail fetch fails

                notifications.append(notif)

            await browser.close()

            # Persist to SQLite so user can read without re-scraping ARCA
            try:
                from backend.services.arca_db import save_notifications

                save_notifications(cuit_for_comms, notifications)
            except Exception:
                pass  # Do not fail the response if DB save fails

            return {
                "success": True,
                "cuit": cuit_for_comms,
                "total": len(notifications),
                "notifications": notifications,
            }

        except Exception as e:
            try:
                await browser.close()
            except Exception:
                pass
            return {"success": False, "error": str(e), "notifications": []}


def _extract_pdf_from_detail(comm_detail: dict[str, Any]) -> bytes | None:
    """
    Extract first PDF attachment from communication detail.
    AFIP API may return adjuntos as array with contenido (base64) or similar.
    """
    adjuntos = comm_detail.get("adjuntos") or comm_detail.get("archivos") or []
    if not isinstance(adjuntos, list):
        return None
    for adj in adjuntos:
        if not isinstance(adj, dict):
            continue
        contenido = adj.get("contenido") or adj.get("content") or adj.get("data")
        if contenido:
            try:
                return base64.b64decode(contenido)
            except Exception:
                pass
        url = adj.get("url") or adj.get("link")
        if url:
            # URL would require fetch in browser context; skip for now
            pass
    return None


def _epoch_ms_to_iso(epoch_ms: int | None) -> str | None:
    """Convert epoch milliseconds to ISO 8601 string."""
    if epoch_ms is None:
        return None
    try:
        return datetime.fromtimestamp(epoch_ms / 1000).isoformat()
    except Exception:
        return None


async def get_representados(cuit: str, password: str) -> dict[str, Any]:
    """
    Fetch list of representados (companies/persons the user represents) from DFE.
    Returns {success, representados: [{cuit, nombre}], error}.
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos", "representados": []}

    auth_data: dict[str, Any] = {}
    api_responses: list[dict] = []

    async def capture_responses(resp):
        url = resp.url
        if "ve.cloud.afip.gob.ar/api" in url and "representad" in url.lower():
            try:
                body = await resp.text()
                api_responses.append({"url": url, "body": body})
            except Exception:
                pass
        if "e-ventanilla/autorizacion" in url:
            try:
                auth_data["data"] = await resp.json()
            except Exception:
                pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()
        page.set_default_timeout(TIMEOUT_MS)
        page.on("response", capture_responses)

        try:
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
                return {"success": False, "error": "Login fallido", "representados": []}

            dfe_link = page.get_by_text("Domicilio Fiscal Electrónico", exact=False)
            await dfe_link.first.wait_for(state="visible", timeout=15000)
            await dfe_link.first.click()
            await asyncio.sleep(8)

            if "data" not in auth_data:
                await browser.close()
                return {"success": False, "error": "No se obtuvo autorización DFE", "representados": []}

            token = auth_data["data"]["token"]
            sign = auth_data["data"]["sign"]
            dfe_url = (
                f"https://ve.cloud.afip.gob.ar/login"
                f"?token={urllib.parse.quote(token)}&sign={urllib.parse.quote(sign)}"
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

            # Try API: /api/v1/representados or similar
            for api_path in ["/api/v1/representados", "/api/v1/represented", "/api/v1/entities"]:
                try:
                    api_url = f"https://ve.cloud.afip.gob.ar{api_path}"
                    resp = await page.evaluate(
                        """async (url) => {
                            const r = await fetch(url);
                            return { status: r.status, body: await r.text() };
                        }""",
                        api_url,
                    )
                    if resp["status"] == 200:
                        data = json.loads(resp["body"])
                        items = data.get("representados") or data.get("entities") or data.get("data") or []
                        if isinstance(items, list) and items:
                            result = []
                            for it in items:
                                c = "".join(x for x in str(it.get("cuit") or it.get("cuitRepresentado") or "") if x.isdigit())
                                n = it.get("nombre") or it.get("razonSocial") or it.get("name") or ""
                                if len(c) == 11:
                                    result.append({"cuit": c, "nombre": n})
                            if result:
                                await browser.close()
                                try:
                                    from backend.services.arca_db import save_representados
                                    save_representados(cuit_clean, result)
                                except Exception:
                                    pass
                                return {"success": True, "representados": result}
                except Exception:
                    pass

            # Fallback: scrape "Comunicaciones de mis representados" list from DOM
            try:
                tab = page.get_by_text("Comunicaciones de mis representados", exact=False)
                await tab.first.click()
                await asyncio.sleep(5)
                list_text = await page.evaluate("""() => {
                    const list = document.querySelector('[class*="representad"], [class*="list"], [role="listbox"]');
                    if (list) return list.innerText;
                    const items = document.querySelectorAll('li, [role="option"], [class*="item"]');
                    return Array.from(items).map(el => el.innerText).join('\\n');
                }""")
                representados = []
                for line in (list_text or "").split("\n"):
                    line = line.strip()
                    match = re.search(r"(.+?)\s*[-–]\s*(\d{10,11})\s*$", line)
                    if match:
                        nombre, cuit = match.group(1).strip(), "".join(c for c in match.group(2) if c.isdigit())
                        if len(cuit) == 11:
                            representados.append({"cuit": cuit, "nombre": nombre})
                if representados:
                    try:
                        from backend.services.arca_db import save_representados
                        save_representados(cuit_clean, representados)
                    except Exception:
                        pass
                    await browser.close()
                    return {"success": True, "representados": representados}
            except Exception:
                pass

            await browser.close()
            return {
                "success": True,
                "representados": [],
                "message": "No se encontraron representados. Agregue CUIT manualmente.",
            }

        except Exception as e:
            try:
                await browser.close()
            except Exception:
                pass
            return {"success": False, "error": str(e), "representados": []}


def _classify(tipo: int | None, prioridad: int | None) -> str:
    """Map tipo/prioridad to a human-readable classification."""
    if tipo == 2:
        return "Notificaciones"
    if prioridad == 3:
        return "Otros mensajes"
    if prioridad == 1 and tipo == 1:
        return "Avisos"
    return "Otros mensajes"
