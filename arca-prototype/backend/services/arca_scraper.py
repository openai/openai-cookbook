"""
ARCA scraper service using Playwright.
Handles login with CUIT + Clave Fiscal and basic navigation.
"""
import asyncio
import os
import re
import urllib.parse
from typing import Any

from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout

# ARCA login URLs (configurable via env)
ARCA_LOGIN_URL = os.getenv("ARCA_LOGIN_URL", "https://auth.afip.gob.ar/contribuyente/")
ARCA_ALT_LOGIN = os.getenv(
    "ARCA_ALT_LOGIN",
    "https://auth.arca.gob.ar/contribuyente_/login.xhtml?action=SYSTEM&system=radig_emp",
)
HEADLESS = os.getenv("ARCA_HEADLESS", "true").lower() == "true"
TIMEOUT_MS = int(os.getenv("ARCA_TIMEOUT_MS", "30000"))


async def login_and_scrape(cuit: str, password: str) -> dict[str, Any]:
    """
    Log in to ARCA with CUIT and Clave Fiscal, then return page state.

    Args:
        cuit: CUIT/CUIL number (11 digits, may include dashes)
        password: Clave Fiscal password

    Returns:
        Dict with success status, message, and optional extracted data.
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {
            "success": False,
            "message": "CUIT debe tener 11 dígitos",
            "data": None,
        }

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )
        page: Page = await context.new_page()
        page.set_default_timeout(TIMEOUT_MS)

        try:
            await page.goto(ARCA_LOGIN_URL, wait_until="networkidle")
            await asyncio.sleep(2)

            # Step 1: AFIP uses two-step login - first CUIT, then password
            # Selectors from actual DOM: F1:username, F1:btnSiguiente
            cuit_input = page.locator('input[name="F1:username"]')
            await cuit_input.wait_for(state="visible", timeout=10000)
            await cuit_input.fill(cuit_clean)

            siguiente_btn = page.locator('input[name="F1:btnSiguiente"]')
            await siguiente_btn.click()
            await asyncio.sleep(3)

            # Step 2: Password page - F1:password, F1:btnIngresar
            password_input = page.locator('input[name="F1:password"]')
            await password_input.wait_for(state="visible", timeout=10000)
            await password_input.fill(password)

            ingresar_btn = page.locator('input[name="F1:btnIngresar"]')
            await ingresar_btn.click()
            await asyncio.sleep(4)

            # Check for success: URL change or absence of login form
            current_url = page.url
            if "login" in current_url.lower() or "auth" in current_url.lower():
                # Might still be on login - check for error messages
                error_el = page.locator(
                    '.error, .alert-danger, [class*="error"], [role="alert"]'
                ).first
                if await error_el.count() > 0:
                    error_text = await error_el.text_content()
                    return {
                        "success": False,
                        "message": f"Error de login: {error_text or 'Credenciales inválidas'}",
                        "data": None,
                    }
                return {
                    "success": False,
                    "message": "Login fallido. Verifique CUIT y Clave Fiscal.",
                    "data": None,
                }

            # Login likely succeeded - extract basic page info
            title = await page.title()
            body_text = await page.locator("body").inner_text()
            body_preview = body_text[:500].strip() if body_text else ""

            await browser.close()

            return {
                "success": True,
                "message": "Login exitoso",
                "data": {
                    "page_title": title,
                    "current_url": current_url,
                    "body_preview": body_preview,
                },
            }

        except PlaywrightTimeout as e:
            await browser.close()
            return {
                "success": False,
                "message": f"Timeout: {str(e)}",
                "data": None,
            }
        except Exception as e:
            await browser.close()
            return {
                "success": False,
                "message": str(e),
                "data": None,
            }


async def open_domicilio_fiscal_electronico(cuit: str, password: str) -> dict[str, Any]:
    """
    Log in to ARCA, navigate to Domicilio Fiscal Electrónico, and extract content.
    Returns notifications, comprobantes info, and page structure.

    Args:
        cuit: CUIT/CUIL number (11 digits)
        password: Clave Fiscal

    Returns:
        Dict with success status and DFE page content (notifications, etc.).
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {
            "success": False,
            "message": "CUIT debe tener 11 dígitos",
            "data": None,
        }

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )
        page: Page = await context.new_page()
        page.set_default_timeout(TIMEOUT_MS)

        try:
            await page.goto(ARCA_LOGIN_URL, wait_until="networkidle")
            await asyncio.sleep(2)

            # Step 1: CUIT
            await page.locator('input[name="F1:username"]').fill(cuit_clean)
            await page.locator('input[name="F1:btnSiguiente"]').click()
            await asyncio.sleep(3)

            # Step 2: Password
            await page.locator('input[name="F1:password"]').fill(password)
            await page.locator('input[name="F1:btnIngresar"]').click()
            await asyncio.sleep(5)

            current_url = page.url
            if "login" in current_url.lower() or "auth" in current_url.lower():
                error_el = page.locator('.error, .alert-danger, [class*="error"]').first
                error_text = (
                    await error_el.text_content() if await error_el.count() > 0 else None
                )
                await browser.close()
                return {
                    "success": False,
                    "message": error_text or "Login fallido. Verifique credenciales.",
                    "data": None,
                }

            # Step 3: Navigate to Domicilio Fiscal Electrónico
            # Try multiple selectors - portal may use links, buttons, or menu items
            dfe_locator = page.get_by_text("Domicilio Fiscal Electrónico", exact=False)
            await dfe_locator.first.wait_for(state="visible", timeout=10000)
            await dfe_locator.first.click()
            await asyncio.sleep(4)

            # Extract DFE page content
            body_text = await page.locator("body").inner_text()
            title = await page.title()
            dfe_url = page.url

            # Try to extract structured info: notifications, comprobantes, alerts
            notifications = []
            comprobantes = []
            alerts = []

            # Look for notification-like patterns in the text
            lines = body_text.split("\n")
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                if "notific" in line.lower() or "tenés notificaciones" in line.lower():
                    notifications.append({"text": line, "context": lines[i - 1 : i + 2]})
                if "comprobante" in line.lower() or "mis comprobantes" in line.lower():
                    comprobantes.append({"text": line, "context": lines[i - 1 : i + 2]})
                if "representado" in line.lower() or "domicilio" in line.lower():
                    if "sin" in line.lower() or "no tiene" in line.lower():
                        alerts.append(line)

            await browser.close()

            return {
                "success": True,
                "message": "Domicilio Fiscal Electrónico cargado",
                "data": {
                    "page_title": title,
                    "current_url": dfe_url,
                    "body_full": body_text,
                    "body_preview": body_text[:1500].strip(),
                    "notifications_found": notifications,
                    "comprobantes_found": comprobantes,
                    "alerts": alerts,
                },
            }

        except PlaywrightTimeout as e:
            await browser.close()
            return {
                "success": False,
                "message": f"Timeout: {str(e)}",
                "data": None,
            }
        except Exception as e:
            await browser.close()
            return {
                "success": False,
                "message": str(e),
                "data": None,
            }


async def read_all_notifications(cuit: str, password: str) -> dict[str, Any]:
    """
    Log in, get DFE token, open DFE app, and extract full notification list.
    Returns structured list with asunto, organismo, clasificacion, recibido.
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "message": "CUIT debe tener 11 dígitos", "data": None}

    auth_data = {}
    timeout = int(os.getenv("ARCA_TIMEOUT_MS", "45000"))

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()
        page.set_default_timeout(timeout)

        async def capture_auth(resp):
            if "e-ventanilla/autorizacion" in resp.url:
                try:
                    auth_data["data"] = await resp.json()
                except Exception:
                    pass

        page.on("response", capture_auth)

        try:
            await page.goto(ARCA_LOGIN_URL, wait_until="networkidle")
            await asyncio.sleep(2)
            await page.locator('input[name="F1:username"]').fill(cuit_clean)
            await page.locator('input[name="F1:btnSiguiente"]').click()
            await asyncio.sleep(3)
            await page.locator('input[name="F1:password"]').fill(password)
            await page.locator('input[name="F1:btnIngresar"]').click()
            await asyncio.sleep(8)

            if "login" in page.url.lower():
                await browser.close()
                return {"success": False, "message": "Login fallido", "data": None}

            await page.get_by_text("Domicilio Fiscal Electrónico", exact=False).first.click()
            await asyncio.sleep(10)

            if "data" not in auth_data:
                await browser.close()
                return {"success": False, "message": "No se obtuvo autorización DFE", "data": None}

            token = auth_data["data"]["token"]
            sign = auth_data["data"]["sign"]
            dfe_url = f"https://ve.cloud.afip.gob.ar/login?token={urllib.parse.quote(token)}&sign={urllib.parse.quote(sign)}"

            await page.goto(dfe_url, wait_until="networkidle")
            await asyncio.sleep(5)

            body = await page.locator("body").inner_text()
            await browser.close()

            notifications = []
            date_re = re.compile(r"\d{2}/\d{2}/\d{4}")
            subjects = [
                "Sistema Informático Malvina",
                "Sistema de Cuentas Tributarias",
                "Régimen Percepción IVA - Plataformas Digitales",
            ]
            lines = body.split("\n")
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if any(s in line for s in subjects):
                    notif = {"asunto": line, "organismo": "ARCA", "clasificacion": "", "recibido": ""}
                    for j in range(i + 1, min(i + 6, len(lines))):
                        l2 = lines[j].strip()
                        if date_re.match(l2):
                            notif["recibido"] = l2
                            break
                        if l2 in ("Otros mensajes", "Notificaciones", "Avisos"):
                            notif["clasificacion"] = l2
                    notifications.append(notif)
                i += 1

            return {
                "success": True,
                "message": f"{len(notifications)} notificaciones encontradas",
                "data": {
                    "notifications": notifications,
                    "total": len(notifications),
                    "full_list_preview": body[:2500],
                },
            }

        except Exception as e:
            await browser.close()
            return {"success": False, "message": str(e), "data": None}
