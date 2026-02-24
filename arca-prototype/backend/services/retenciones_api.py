"""
ARCA Mis Retenciones API — fetches retenciones y percepciones via Playwright.

Target app: Mirequa (https://mirequa-web.arca.gob.ar) — a Vue.js SPA using
EDA components (e-input, e-check-item, multiselect, e-date-picker, etc.).

Flow:
  1. Login to ARCA portal (CUIT + Clave Fiscal)
  2. Search for "Mis Retenciones" → opens Mirequa in new tab
  3. Check "Exportar para aplicativos SIAP" checkbox
  4. Select Impuesto from Vue multiselect (#selectImpuestos)
  5. Select Tipo de operación (radio buttons: Retención / Percepción)
  6. Fill date fields (e-date-picker inputs, DD/MM/AAAA format)
  7. Click "Consultar" and wait for results
  8. Intercept Mirequa JSON API response, paginate, return structured data
"""
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright, Page

ARCA_LOGIN_URL = os.getenv("ARCA_LOGIN_URL", "https://auth.afip.gob.ar/contribuyente/")
TIMEOUT_MS = int(os.getenv("ARCA_TIMEOUT_MS", "60000"))
HEADLESS = os.getenv("ARCA_HEADLESS", "true").lower() == "true"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEBUG_DIR = DATA_DIR / "debug"

# Impuesto codes used in the multiselect option IDs
IMPUESTO_OPTIONS = {
    "767": "IMP_767",   # SICORE - RETENCIONES Y PERCEPC (most common)
    "216": "IMP_216",   # SIRE - IVA
    "217": "IMP_217",   # SICORE - IMPTO.A LAS GANANCIAS
    "219": "IMP_219",   # SICORE - IMPTO.S/ BS PERSONALES
    "353": "SS_353",    # RETENCIONES CONTRIB.SEG.SOCIAL
}

# Periodo fiscal format per impuesto code
# YYYYMM (6 chars) for monthly impuestos, YYYY (4 chars) for annual ones
PERIODO_FORMAT = {
    "767": 6,   # SICORE - monthly
    "216": 6,   # SIRE IVA - monthly
    "217": 4,   # Ganancias - annual
    "219": 4,   # Bienes Personales - annual
    "353": 6,   # Seg. Social - monthly
}


def _make_error(error: str, **extra) -> dict[str, Any]:
    """Build a standard error response."""
    return {
        "success": False,
        "error": error,
        "file_path": None,
        "content": None,
        "row_count": 0,
        **extra,
    }


def _make_success(output_path: Path, content: str) -> dict[str, Any]:
    """Build a standard success response from saved CSV content."""
    lines = [ln for ln in content.strip().split("\n") if ln.strip()]
    row_count = max(0, len(lines) - 1) if lines else 0
    return {
        "success": True,
        "message": f"Descargadas {row_count} retenciones",
        "file_path": str(output_path),
        "filename": output_path.name,
        "content_preview": content[:2000] if content else "",
        "row_count": row_count,
        "total_lines": len(lines),
    }


CSV_FIELDS = [
    "fechaRetencion", "cuitAgenteRetencion", "descripcionOperacion",
    "impuestoRetenido", "codigoRegimen", "numeroCertificado",
    "importeRetenido", "numeroComprobante", "fechaComprobante",
    "descripcionComprobante", "fechaIngreso", "codSeguridad",
]


def _make_json_success(output_path: Path, retenciones: list[dict], total: int) -> dict[str, Any]:
    """Build success response from structured JSON retenciones data. Also saves CSV."""
    import csv
    import io

    # Also write CSV alongside the JSON
    csv_path = output_path.with_suffix(".csv")
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for r in retenciones:
        writer.writerow({k: r.get(k, "") for k in CSV_FIELDS})
    csv_content = buf.getvalue()
    csv_path.write_text(csv_content, encoding="utf-8")

    return {
        "success": True,
        "message": f"Descargadas {len(retenciones)} retenciones (total: {total})",
        "file_path": str(csv_path),
        "filename": csv_path.name,
        "json_path": str(output_path),
        "row_count": len(retenciones),
        "total_elements": total,
        "retenciones": retenciones,
        "content_preview": csv_content[:2000],
    }


def _is_csv_content(content: str) -> bool:
    """Check if content looks like CSV/text data, not HTML or JSON."""
    stripped = content.strip()
    if stripped.startswith("<!DOCTYPE") or stripped.startswith("<html"):
        return False
    if "<head>" in stripped[:500] or "<body>" in stripped[:500]:
        return False
    if stripped.startswith("{") or stripped.startswith("["):
        return False
    return True


async def _save_debug_screenshot(page: Page, name: str) -> str | None:
    """Save a debug screenshot and return its path."""
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        path = DEBUG_DIR / f"retenciones_{name}_{datetime.now().strftime('%H%M%S')}.png"
        await page.screenshot(path=path, full_page=True)
        return str(path)
    except Exception:
        return None


async def download_retenciones(
    cuit: str,
    password: str,
    fecha_desde: str,
    fecha_hasta: str,
    id_contribuyente: int = 0,
    impuesto: str = "767",
    tipo_operacion: str = "retencion",
    output_path: Path | None = None,
) -> dict[str, Any]:
    """
    Download retenciones y percepciones from Mis Retenciones (Exportar para Aplicativo).

    Args:
        cuit: CUIT/CUIL (11 digits)
        password: Clave Fiscal
        fecha_desde: Start date DD/MM/YYYY
        fecha_hasta: End date DD/MM/YYYY
        id_contribuyente: 0-based index of persona to select (0 = first)
        impuesto: Impuesto code — "767" (default, SICORE Ret y Perc), "216" (IVA), "217" (Ganancias)
        tipo_operacion: "retencion" or "percepcion"
        output_path: Where to save the CSV. Default: data/retenciones_{cuit}_{timestamp}.csv

    Returns:
        Dict with success, message, file_path, content_preview, row_count.
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return _make_error("CUIT debe tener 11 dígitos")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = DATA_DIR / f"retenciones_{cuit_clean}_{ts}.csv"

    # Collect intercepted API info for diagnostics
    api_calls: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            accept_downloads=True,
        )
        page = await context.new_page()
        page.set_default_timeout(TIMEOUT_MS)

        try:
            # ================================================================
            # STEP 1: Login to ARCA portal
            # ================================================================
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
                return _make_error("Login fallido. Verifique CUIT y Clave Fiscal.")

            # ================================================================
            # STEP 2: Open "Mis Retenciones" via search bar → Mirequa app
            # ================================================================
            search_input = page.locator("#buscadorInput")
            await search_input.wait_for(state="visible", timeout=15000)
            await search_input.fill("Mis Retenciones")
            await asyncio.sleep(2)

            menu_item = page.locator(".rbt-menu a, .rbt-menu li").first
            if await menu_item.count() > 0:
                await menu_item.click()
            else:
                await search_input.press("Enter")
            await asyncio.sleep(10)

            # Mirequa opens in a new tab
            all_pages = context.pages
            mret = page
            if len(all_pages) >= 2:
                mret = all_pages[-1]

            # Wait for Mirequa Vue app to fully render
            try:
                await mret.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await asyncio.sleep(3)

            # Set up network interception — capture full body for API calls
            async def intercept_response(response):
                url = response.url
                if any(pat in url.lower() for pat in ["/api/", "retenciones", "consulta", "exportar", "download"]):
                    try:
                        body = await response.text()
                    except Exception:
                        body = ""
                    api_calls.append({
                        "url": url,
                        "status": response.status,
                        "body": body,
                    })

            mret.on("response", intercept_response)

            await _save_debug_screenshot(mret, "01_mirequa_loaded")

            # ================================================================
            # STEP 3: Check "Exportar para aplicativos SIAP" checkbox
            # ================================================================
            # This must be done FIRST — it changes the form layout and clears dates
            siap_checkbox = mret.locator("#exportarAplicativoCheck_input")
            if await siap_checkbox.count() > 0:
                is_checked = await siap_checkbox.is_checked()
                if not is_checked:
                    await siap_checkbox.click()
                    await asyncio.sleep(2)  # Wait for form to update with new fields

            # ================================================================
            # STEP 4: Select Impuesto from Vue multiselect
            # ================================================================
            # The multiselect input: #selectImpuestos (role="combobox")
            # Options listbox: #selectImpuestos-multiselect-options
            # Option IDs follow pattern: #selectImpuestos-multiselect-option-{IMP_code}
            impuesto_code = IMPUESTO_OPTIONS.get(impuesto, f"IMP_{impuesto}")
            option_id = f"selectImpuestos-multiselect-option-{impuesto_code}"

            # Click the multiselect to open dropdown
            multiselect_input = mret.locator("#selectImpuestos")
            await multiselect_input.click()
            await asyncio.sleep(1)

            # Click the specific option by its known ID
            option_el = mret.locator(f"#{option_id}")
            if await option_el.count() > 0:
                await option_el.click()
                await asyncio.sleep(1)
            else:
                # Fallback: try clicking by text content
                option_by_text = mret.locator(
                    f"#selectImpuestos-multiselect-options .multiselect-option:has-text('{impuesto}')"
                )
                if await option_by_text.count() > 0:
                    await option_by_text.first.click()
                    await asyncio.sleep(1)
                else:
                    # Click away to close dropdown
                    await mret.keyboard.press("Escape")

            # Close multiselect dropdown completely before interacting with other fields
            await mret.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            # Click the page title to ensure focus leaves the multiselect
            title_el = mret.locator("h1, h2, .e-tabs-nav-link").first
            if await title_el.count() > 0:
                await title_el.click()
            await asyncio.sleep(1)

            # ================================================================
            # STEP 5: Select Tipo de operación (radio buttons)
            # ================================================================
            # After selecting impuesto, "Tipo de operación *" appears with:
            #   <label class="form-check-label">
            #     <input type="radio" class="e-check-item--checker" value="1"> Retención
            #   </label>
            #   <label class="form-check-label">
            #     <input type="radio" class="e-check-item--checker" value="2"> Percepción
            #   </label>
            # Radio IDs are dynamic (__EVID__*), so we select by value:
            #   value="1" = Retención, value="2" = Percepción
            if tipo_operacion.lower().startswith("percep"):
                radio_value = "2"
            else:
                radio_value = "1"

            # Click the actual radio input by value
            radio_input = mret.locator(f'input[type="radio"][value="{radio_value}"]')
            if await radio_input.count() > 0:
                await radio_input.click(force=True)
                await asyncio.sleep(0.5)
            else:
                # Fallback: click by label text
                radio_label = "Percepción" if radio_value == "2" else "Retención"
                label_el = mret.locator(f"label.form-check-label:has-text('{radio_label}')").first
                if await label_el.count() > 0:
                    await label_el.click()
                    await asyncio.sleep(0.5)

            # ================================================================
            # STEP 6: Fill period — date fields OR periodoFiscal
            # ================================================================
            # The form requires at least ONE of:
            #   - Fecha de retención (desde + hasta)
            #   - Fecha comprobante (desde + hasta)
            #   - Período fiscal (AAAAMM format)
            #
            # The EDA date picker component re-renders after the first field
            # is set, which resets the second field. To work around this, we
            # use a dual approach:
            #   A. Try filling both dates atomically via Playwright (hasta first)
            #   B. If dates fail, use periodoFiscal as a reliable fallback

            # --- Strategy A: Fill dates in reverse order (hasta first) ---
            # Filling hasta before desde avoids the re-render issue since
            # the component re-renders AFTER desde is set (not hasta).
            dates_filled = 0
            for field_id, date_value in [
                ("#datePickerFechasRetencionesHasta__input", fecha_hasta),
                ("#datePickerFechasRetencionesDesde__input", fecha_desde),
            ]:
                field = mret.locator(field_id)
                if await field.count() == 0:
                    continue
                await field.click()
                await asyncio.sleep(0.3)
                await mret.keyboard.press("Escape")  # dismiss calendar popup
                await asyncio.sleep(0.3)
                await field.fill(date_value)
                await asyncio.sleep(0.5)
                # Dismiss popup and move focus away
                await mret.keyboard.press("Escape")
                await asyncio.sleep(0.2)

            # Click elsewhere to blur all date pickers
            await mret.locator("h1, h2, .e-tabs-nav-link").first.click()
            await asyncio.sleep(0.5)

            desde_val = await mret.locator("#datePickerFechasRetencionesDesde__input").input_value()
            hasta_val = await mret.locator("#datePickerFechasRetencionesHasta__input").input_value()
            dates_filled = (1 if desde_val and len(desde_val) >= 8 else 0) + \
                           (1 if hasta_val and len(hasta_val) >= 8 else 0)

            # --- Strategy B: If dates didn't stick, use periodoFiscal ---
            if dates_filled < 2:
                periodo_field = mret.locator("#periodoFiscal")
                if await periodo_field.count() > 0:
                    parts_d = fecha_desde.split("/")
                    year = parts_d[2] if len(parts_d) == 3 else fecha_desde[:4]
                    month = parts_d[1] if len(parts_d) == 3 else "01"

                    # Use PERIODO_FORMAT map to determine correct length
                    periodo_len = PERIODO_FORMAT.get(impuesto, 6)
                    if periodo_len == 6:
                        # AAAAMM format (e.g. SICORE 767, IVA 216)
                        periodo = f"{year}{month}"
                    else:
                        # AAAA format (e.g. Ganancias 217, Bs Personales 219)
                        periodo = year

                    await periodo_field.click()
                    await periodo_field.fill(periodo)
                    await asyncio.sleep(0.3)

                    # Also try to fill the hasta date one more time via JS
                    if not hasta_val or len(hasta_val) < 8:
                        await mret.evaluate(
                            """(args) => {
                                const el = document.getElementById(args.id);
                                if (!el) return;
                                const setter = Object.getOwnPropertyDescriptor(
                                    window.HTMLInputElement.prototype, 'value'
                                ).set;
                                setter.call(el, args.value);
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                            }""",
                            {"id": "datePickerFechasRetencionesHasta__input", "value": fecha_hasta},
                        )
                        await asyncio.sleep(0.3)

            await _save_debug_screenshot(mret, "03_form_filled")

            # ================================================================
            # STEP 7: Click "Consultar" and handle response
            # ================================================================
            consultar = mret.locator("button:has-text('Consultar')").first
            if await consultar.count() == 0:
                debug_path = await _save_debug_screenshot(mret, "04_no_consultar")
                body_text = await mret.locator("body").inner_text()
                await browser.close()
                return _make_error(
                    "No se encontró el botón 'Consultar'.",
                    debug_screenshot=debug_path,
                    page_url=mret.url,
                    page_preview=body_text[:2000],
                )

            # Try to capture download if Consultar triggers one directly
            download_captured = False
            try:
                async with mret.expect_download(timeout=30000) as download_info:
                    await consultar.click()
                download = await download_info.value
                await download.save_as(output_path)
                content = output_path.read_text(encoding="utf-8", errors="replace")
                if _is_csv_content(content):
                    await browser.close()
                    return _make_success(output_path, content)
                # Downloaded HTML instead of CSV — form had validation errors
                download_captured = False
            except Exception:
                pass

            # Wait for results to load
            await asyncio.sleep(8)
            await _save_debug_screenshot(mret, "05_after_consultar")

            # Check for validation errors
            body_text = await mret.locator("body").inner_text()
            error_patterns = [
                r"Se encontr(?:aron|ó) \d+ errores?",
                "Seleccioná un impuesto",
                "Seleccioná un tipo de operación",
                "Ingresá al menos una opción",
                "fecha desde y hasta",
            ]
            for pat in error_patterns:
                if re.search(pat, body_text, re.IGNORECASE):
                    debug_path = await _save_debug_screenshot(mret, "06_validation_error")
                    await browser.close()
                    # Extract just the error section
                    error_match = re.search(r"Se encontr(?:aron|ó).+?(?=\*|Campos obligatorios)", body_text, re.DOTALL)
                    error_detail = error_match.group(0).strip() if error_match else body_text[:500]
                    return _make_error(
                        f"Errores de validación en el formulario: {error_detail}",
                        debug_screenshot=debug_path,
                        page_url=mret.url,
                        dates_filled=dates_filled,
                        desde_value=desde_val,
                        hasta_value=hasta_val,
                    )

            # Check for "no results"
            if any(msg in body_text.lower() for msg in ["no se encontraron", "sin resultado", "no hay datos", "0 resultados"]):
                await browser.close()
                return _make_error(
                    "La consulta no arrojó resultados. Verifique el rango de fechas.",
                    page_preview=body_text[:2000],
                )

            # ================================================================
            # STEP 8: Capture data — JSON API interception + CSV fallbacks
            # ================================================================

            # Strategy 1 (best): Check intercepted API calls for JSON retenciones
            # Mirequa's Vue app calls its backend API which returns paginated JSON:
            #   {"page":{"size":10,"totalElements":N,"totalPages":P,"number":0},
            #    "retenciones":[{...}, ...]}
            api_url = None
            first_page_data = None
            for call in api_calls:
                body = call.get("body", "")
                if not body or call.get("status", 0) != 200:
                    continue
                try:
                    parsed = json.loads(body)
                    if isinstance(parsed, dict) and "retenciones" in parsed and "page" in parsed:
                        api_url = call["url"]
                        first_page_data = parsed
                        break
                except (json.JSONDecodeError, ValueError):
                    continue

            if first_page_data and api_url:
                # Paginate through all results
                page_info = first_page_data["page"]
                total_elements = page_info.get("totalElements", 0)
                total_pages = page_info.get("totalPages", 1)
                all_retenciones = list(first_page_data["retenciones"])

                for page_num in range(1, total_pages):
                    # Build URL for next page
                    if "page=" in api_url:
                        paged_url = re.sub(r"page=\d+", f"page={page_num}", api_url)
                    elif "?" in api_url:
                        paged_url = f"{api_url}&page={page_num}"
                    else:
                        paged_url = f"{api_url}?page={page_num}"
                    try:
                        page_text = await mret.evaluate(
                            "async (url) => { const r = await fetch(url); return await r.text(); }",
                            paged_url,
                        )
                        page_data = json.loads(page_text)
                        if "retenciones" in page_data:
                            all_retenciones.extend(page_data["retenciones"])
                    except Exception:
                        break
                    await asyncio.sleep(0.3)

                # Save as JSON
                json_path = output_path.with_suffix(".json")
                json_path.write_text(
                    json.dumps(all_retenciones, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8",
                )
                await browser.close()
                return _make_json_success(json_path, all_retenciones, total_elements)

            # Strategy 2: "Exportar" / "Descargar" buttons → CSV download
            export_selectors = [
                "button:has-text('Exportar todos')",
                "button:has-text('Exportar para Aplicativo')",
                "button:has-text('Exportar para aplicativos')",
                "button:has-text('Exportar')",
                "button:has-text('Descargar')",
                "a:has-text('Exportar')",
                "a:has-text('Descargar')",
            ]
            for sel in export_selectors:
                el = mret.locator(sel).first
                if await el.count() > 0:
                    try:
                        async with mret.expect_download(timeout=30000) as download_info:
                            await el.click()
                        download = await download_info.value
                        await download.save_as(output_path)
                        content = output_path.read_text(encoding="utf-8", errors="replace")
                        if _is_csv_content(content):
                            await browser.close()
                            return _make_success(output_path, content)
                    except Exception:
                        continue

            # Strategy 3: Download links with href
            download_links = mret.locator("a[href*='download'], a[href*='exportar'], a[href*='csv'], a[download]")
            if await download_links.count() > 0:
                href = await download_links.first.get_attribute("href")
                if href:
                    try:
                        csv_data = await mret.evaluate(
                            """async (url) => {
                                const fullUrl = url.startsWith('http') ? url : window.location.origin + url;
                                const r = await fetch(fullUrl);
                                if (!r.ok) return { error: 'HTTP ' + r.status, content: '' };
                                return { error: null, content: await r.text() };
                            }""",
                            href,
                        )
                        if csv_data.get("content") and _is_csv_content(csv_data["content"]):
                            output_path.write_text(csv_data["content"], encoding="utf-8")
                            await browser.close()
                            return _make_success(output_path, csv_data["content"])
                    except Exception:
                        pass

            # ================================================================
            # All strategies exhausted — return diagnostics
            # ================================================================
            debug_path = await _save_debug_screenshot(mret, "09_all_failed")
            await browser.close()
            return _make_error(
                "No se pudo descargar el archivo de retenciones. "
                "La consulta parece haberse ejecutado pero no se capturó el CSV.",
                debug_screenshot=debug_path,
                page_url=mret.url,
                page_preview=body_text[:2000] if body_text else "",
                api_calls_discovered=len(api_calls),
                api_calls_detail=[
                    {"url": c["url"], "status": c["status"], "body_preview": c.get("body", "")[:200]}
                    for c in api_calls[:10]
                ],
            )

        except Exception as e:
            debug_path = await _save_debug_screenshot(
                mret if "mret" in dir() else page, "99_exception"
            )
            try:
                await browser.close()
            except Exception:
                pass
            return _make_error(
                str(e),
                debug_screenshot=debug_path,
                api_calls_discovered=len(api_calls),
            )
