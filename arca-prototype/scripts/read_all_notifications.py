"""
Read all DFE notification pages and extract full content.
Explores: DFE main, notifications list, notificaciones a mis representados.
"""
import asyncio
import json
import os
import sys

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
        print("Error: Set ARCA_CUIT and ARCA_PASSWORD in .env")
        sys.exit(1)

    cuit_clean = "".join(c for c in cuit if c.isdigit())

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )
        page = await context.new_page()
        page.set_default_timeout(TIMEOUT_MS)

        pages_read = []

        try:
            # Login
            await page.goto(ARCA_LOGIN_URL, wait_until="networkidle")
            await asyncio.sleep(2)
            await page.locator('input[name="F1:username"]').fill(cuit_clean)
            await page.locator('input[name="F1:btnSiguiente"]').click()
            await asyncio.sleep(3)
            await page.locator('input[name="F1:password"]').fill(password)
            await page.locator('input[name="F1:btnIngresar"]').click()
            await asyncio.sleep(5)

            if "login" in page.url.lower():
                print(json.dumps({"success": False, "message": "Login failed"}))
                await browser.close()
                return

            # Page 1: Portal home
            body1 = await page.locator("body").inner_text()
            pages_read.append({"name": "Portal home", "url": page.url, "content": body1})

            # Click Domicilio Fiscal Electrónico
            dfe = page.get_by_text("Domicilio Fiscal Electrónico", exact=False)
            await dfe.first.click()
            await asyncio.sleep(4)

            # Check for iframes
            frames = page.frames
            main_content = body1
            if len(frames) > 1:
                for f in frames:
                    try:
                        txt = await f.locator("body").inner_text()
                        if "notific" in txt.lower() or "representado" in txt.lower():
                            main_content = txt
                            break
                    except Exception:
                        pass

            body2 = await page.locator("body").inner_text()
            pages_read.append({"name": "After DFE click", "url": page.url, "content": body2})

            # Try to click "Tenés notificaciones" to open notifications list
            notif_link = page.get_by_text("Tenés notificaciones", exact=False)
            if await notif_link.count() > 0:
                await notif_link.first.click()
                await asyncio.sleep(4)
                body3 = await page.locator("body").inner_text()
                pages_read.append({"name": "Notifications view", "url": page.url, "content": body3})

            # Try "notificaciones a mis representados" or similar
            rep_link = page.get_by_text("representado", exact=False)
            for i in range(min(5, await rep_link.count())):
                try:
                    el = rep_link.nth(i)
                    txt = await el.text_content()
                    if txt and "notific" in txt.lower():
                        await el.click()
                        await asyncio.sleep(4)
                        body_rep = await page.locator("body").inner_text()
                        pages_read.append(
                            {"name": f"Representados: {txt[:50]}", "url": page.url, "content": body_rep}
                        )
                        break
                except Exception:
                    pass

            # Get all links on page for "notificaciones"
            all_links = await page.evaluate(
                """() => {
                const links = document.querySelectorAll('a, [role="button"], button');
                return Array.from(links).filter(el => {
                    const t = (el.textContent || '').toLowerCase();
                    return t.includes('notific') || t.includes('comprobante') || t.includes('representado');
                }).map(el => ({ text: el.textContent?.trim().slice(0,60), tag: el.tagName }));
            }"""
            )

            await browser.close()

            result = {
                "success": True,
                "pages_read": pages_read,
                "links_found": all_links,
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))

        except Exception as e:
            await browser.close()
            print(json.dumps({"success": False, "message": str(e), "pages_read": pages_read}))


if __name__ == "__main__":
    asyncio.run(main())
