"""
Log into ARCA, access DFE with token, extract notification list and open each to get content.
"""
import asyncio
import json
import os
import sys
import re
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from playwright.async_api import async_playwright

ARCA_LOGIN_URL = "https://auth.afip.gob.ar/contribuyente/"
TIMEOUT_MS = 45000


async def main():
    cuit = os.getenv("ARCA_CUIT", "").strip()
    password = os.getenv("ARCA_PASSWORD", "").strip()
    if not cuit or not password:
        print(json.dumps({"success": False, "message": "Set ARCA_CUIT and ARCA_PASSWORD in .env"}))
        sys.exit(1)

    cuit_clean = "".join(c for c in cuit if c.isdigit())

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()
        page.set_default_timeout(TIMEOUT_MS)

        auth_data = {}

        async def capture_auth(resp):
            if "e-ventanilla/autorizacion" in resp.url:
                try:
                    auth_data["data"] = await resp.json()
                except Exception:
                    pass

        page.on("response", capture_auth)

        await page.goto(ARCA_LOGIN_URL, wait_until="networkidle")
        await asyncio.sleep(2)
        await page.locator('input[name="F1:username"]').fill(cuit_clean)
        await page.locator('input[name="F1:btnSiguiente"]').click()
        await asyncio.sleep(3)
        await page.locator('input[name="F1:password"]').fill(password)
        await page.locator('input[name="F1:btnIngresar"]').click()
        await asyncio.sleep(8)

        if "login" in page.url.lower():
            print(json.dumps({"success": False, "message": "Login failed"}))
            await browser.close()
            return

        await page.get_by_text("Domicilio Fiscal Electrónico", exact=False).first.click()
        await asyncio.sleep(10)

        if "data" not in auth_data:
            print(json.dumps({"success": False, "message": "No DFE autorizacion"}))
            await browser.close()
            return

        token = auth_data["data"]["token"]
        sign = auth_data["data"]["sign"]
        dfe_url = f"https://ve.cloud.afip.gob.ar/login?token={urllib.parse.quote(token)}&sign={urllib.parse.quote(sign)}"

        await page.goto(dfe_url, wait_until="networkidle")
        await asyncio.sleep(5)

        body = await page.locator("body").inner_text()

        # Parse notifications from table: Asunto, Organismo, Clasificación, Recibido
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

        await browser.close()

        result = {
            "success": True,
            "notifications": notifications,
            "full_list_preview": body[:2500],
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
