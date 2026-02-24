"""
ARCA Mis Comprobantes API — fetches comprobantes (emitidos & recibidos)
via the internal AJAX API at fes.afip.gob.ar/mcmp.

Flow:
  1. Login to ARCA portal via Playwright (CUIT + Clave Fiscal)
  2. Navigate to Mis Comprobantes service (search bar → mcmp)
  3. Select persona (idContribuyente)
  4. Navigate to comprobantesRecibidos.do or comprobantesEmitidos.do
  5. Call ajax.do?f=generarConsulta to create the query
  6. Call ajax.do?f=estimarResultados to check pagination mode
  7. Call ajax.do?f=listaResultados to get the actual data
  8. Return structured JSON
"""
import asyncio
import json
import os
import urllib.parse
from datetime import datetime
from typing import Any, Literal

from playwright.async_api import async_playwright

ARCA_LOGIN_URL = os.getenv("ARCA_LOGIN_URL", "https://auth.afip.gob.ar/contribuyente/")
TIMEOUT_MS = int(os.getenv("ARCA_TIMEOUT_MS", "45000"))
HEADLESS = os.getenv("ARCA_HEADLESS", "true").lower() == "true"
MCMP_BASE = "https://fes.afip.gob.ar/mcmp/jsp"

# Tipo comprobante codes → human-readable names
TIPO_COMPROBANTE = {
    "1": "Factura A", "2": "Nota de Débito A", "3": "Nota de Crédito A", "4": "Recibo A",
    "6": "Factura B", "7": "Nota de Débito B", "8": "Nota de Crédito B", "9": "Recibo B",
    "11": "Factura C", "12": "Nota de Débito C", "13": "Nota de Crédito C", "15": "Recibo C",
    "19": "Factura de Exportación",
    "20": "ND Operaciones con el Exterior", "21": "NC Operaciones con el Exterior",
    "51": "Factura M", "52": "ND M", "53": "NC M", "54": "Recibo M",
    "81": "Tique Factura A", "82": "Tique Factura B", "83": "Tique",
    "109": "Tique C", "110": "Tique NC", "111": "Tique Factura C",
    "112": "Tique NC A", "113": "Tique NC B", "114": "Tique NC C",
    "115": "Tique ND A", "116": "Tique ND B", "117": "Tique ND C",
    "195": "Factura T", "196": "ND T", "197": "NC T",
    "201": "FCE A", "202": "ND FCE A", "203": "NC FCE A",
    "206": "FCE B", "207": "ND FCE B", "208": "NC FCE B",
    "211": "FCE C", "212": "ND FCE C", "213": "NC FCE C",
}

# Tipo documento codes
TIPO_DOC = {
    "80": "CUIT", "86": "CUIL", "96": "DNI",
    "87": "CDI", "89": "LE", "90": "LC",
    "91": "CI Extranjera", "94": "Pasaporte", "99": "Otro",
}


def _parse_importe(raw_value: Any) -> float:
    """Parse importe from ARCA raw value.

    ARCA returns amounts in pesos — both integer ("244299" → $244,299.00)
    and decimal ("3148080.99" → $3,148,080.99) formats.
    No division needed; just convert to float.
    """
    try:
        raw_str = str(raw_value) if raw_value else "0"
        return round(float(raw_str), 2)
    except (ValueError, TypeError):
        return 0.0


def _parse_fecha(fecha_str: str | None) -> tuple[str | None, str]:
    """Return (fecha_iso, fecha_display) from DD/MM/YYYY string."""
    display = fecha_str or ""
    iso = None
    if display:
        try:
            iso = datetime.strptime(display, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            iso = display
    return iso, display


def _parse_comprobante_recibido(raw: list) -> dict[str, Any]:
    """
    Parse a raw RECIBIDO array (52 elements) into a structured dict.

    Field mapping (reverse-engineered):
      [0]  fechaEmision         DD/MM/YYYY
      [1]  tipoComprobante      int code
      [3]  puntoVenta           int
      [4]  nroDesde             int
      [5]  nroHasta             int
      [8]  codAutorizacion      CAE string
      [10] tipoDocEmisor        int code (80=CUIT)
      [11] nroDocEmisor         string (CUIT del emisor)
      [12] denominacionEmisor   string
      [17] moneda               "$" / "USD"
      [50] importeTotal         pesos (int or decimal)
    """
    tipo_code = str(raw[1]) if raw[1] is not None else ""
    tipo_doc_code = str(raw[10]) if raw[10] is not None else ""
    pto_venta = raw[3]
    nro_desde = raw[4]

    if pto_venta is not None and nro_desde is not None:
        numero = f"{int(pto_venta):05d}-{int(nro_desde):08d}"
    else:
        numero = str(nro_desde) if nro_desde else ""

    importe = _parse_importe(raw[50] if len(raw) > 50 else 0)
    fecha_iso, fecha_display = _parse_fecha(raw[0])
    moneda = raw[17] or "$"

    return {
        "fecha_emision": fecha_iso,
        "fecha_emision_display": fecha_display,
        "tipo_comprobante_codigo": int(tipo_code) if tipo_code.isdigit() else None,
        "tipo_comprobante": TIPO_COMPROBANTE.get(tipo_code, f"Tipo {tipo_code}"),
        "punto_venta": int(pto_venta) if pto_venta is not None else None,
        "numero_desde": int(nro_desde) if nro_desde is not None else None,
        "numero_hasta": int(raw[5]) if raw[5] is not None else None,
        "numero": numero,
        "cod_autorizacion": str(raw[8]) if raw[8] else None,
        "tipo_doc_contraparte": TIPO_DOC.get(tipo_doc_code, tipo_doc_code),
        "cuit_contraparte": str(raw[11]) if raw[11] else None,
        "denominacion_contraparte": raw[12] or "",
        "moneda": moneda,
        "importe_total": importe,
        "importe_total_display": f"{moneda}{importe:,.2f}",
    }


def _parse_comprobante_emitido(raw: list) -> dict[str, Any]:
    """
    Parse a raw EMITIDO array (49 elements) into a structured dict.

    Field mapping (reverse-engineered):
      [0]  fechaEmision         DD/MM/YYYY
      [1]  tipoComprobante      int code
      [3]  puntoVenta           int
      [4]  nroDesde             int
      [5]  nroHasta             int
      [8]  codAutorizacion      CAE string
      [10] tipoDocReceptor      int code (80=CUIT)
      [11] nroDocReceptor       string (CUIT del receptor)
      [12] denominacionReceptor string
      [13] tipoCambio           float (1.0 for ARS, e.g. 1036 for USD→ARS)
      [14] moneda               "$" / "USD"
      [29] ivaTotal             float
      [31] netoGravado          float
      [33] netoNoGravado        float (nullable)
      [35] exento               float (nullable)
      [39] otrosTributos1       float
      [41] otrosTributos2       float (nullable)
      [43] otrosTributos3       float
      [47] importeTotal         pesos (int or decimal)
    """
    tipo_code = str(raw[1]) if raw[1] is not None else ""
    tipo_doc_code = str(raw[10]) if raw[10] is not None else ""
    pto_venta = raw[3]
    nro_desde = raw[4]

    if pto_venta is not None and nro_desde is not None:
        numero = f"{int(pto_venta):05d}-{int(nro_desde):08d}"
    else:
        numero = str(nro_desde) if nro_desde else ""

    importe = _parse_importe(raw[47] if len(raw) > 47 else 0)
    fecha_iso, fecha_display = _parse_fecha(raw[0])
    moneda = raw[14] or "$"

    # Tax breakdown fields (discovered 2026-02-24)
    tipo_cambio = _parse_importe(raw[13]) if len(raw) > 13 else 0.0
    neto_gravado = _parse_importe(raw[31]) if len(raw) > 31 else 0.0
    neto_no_gravado = _parse_importe(raw[33]) if len(raw) > 33 else 0.0
    exento = _parse_importe(raw[35]) if len(raw) > 35 else 0.0
    iva_total = _parse_importe(raw[29]) if len(raw) > 29 else 0.0
    otros_tributos = sum(
        _parse_importe(raw[i]) if len(raw) > i else 0.0
        for i in (39, 41, 43)
    )

    return {
        "fecha_emision": fecha_iso,
        "fecha_emision_display": fecha_display,
        "tipo_comprobante_codigo": int(tipo_code) if tipo_code.isdigit() else None,
        "tipo_comprobante": TIPO_COMPROBANTE.get(tipo_code, f"Tipo {tipo_code}"),
        "punto_venta": int(pto_venta) if pto_venta is not None else None,
        "numero_desde": int(nro_desde) if nro_desde is not None else None,
        "numero_hasta": int(raw[5]) if raw[5] is not None else None,
        "numero": numero,
        "cod_autorizacion": str(raw[8]) if raw[8] else None,
        "tipo_doc_contraparte": TIPO_DOC.get(tipo_doc_code, tipo_doc_code),
        "cuit_contraparte": str(raw[11]) if raw[11] else None,
        "denominacion_contraparte": raw[12] or "",
        "moneda": moneda,
        "importe_total": importe,
        "importe_total_display": f"{moneda}{importe:,.2f}",
        "tipo_cambio": tipo_cambio,
        "neto_gravado": neto_gravado,
        "neto_no_gravado": neto_no_gravado,
        "exento": exento,
        "iva_total": iva_total,
        "otros_tributos": otros_tributos,
    }


async def _fetch_comprobantes(
    cuit: str,
    password: str,
    fecha_desde: str,
    fecha_hasta: str,
    tipo: Literal["R", "E"],
    tipos_comprobante: str = "",
    id_contribuyente: int = 1,
) -> dict[str, Any]:
    """
    Shared implementation for fetching comprobantes (recibidos or emitidos).

    Args:
        cuit: CUIT/CUIL (11 digits)
        password: Clave Fiscal
        fecha_desde: Start date DD/MM/YYYY
        fecha_hasta: End date DD/MM/YYYY
        tipo: "R" for recibidos, "E" for emitidos
        tipos_comprobante: Comma-separated tipo codes (empty = all)
        id_contribuyente: 0-based index of persona to select

    Returns:
        Structured JSON with comprobantes list.
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return {"success": False, "error": "CUIT debe tener 11 dígitos", "comprobantes": []}

    page_do = "comprobantesRecibidos.do" if tipo == "R" else "comprobantesEmitidos.do"
    parser = _parse_comprobante_recibido if tipo == "R" else _parse_comprobante_emitido

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()
        page.set_default_timeout(TIMEOUT_MS)

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
                return {
                    "success": False,
                    "error": "Login fallido. Verifique CUIT y Clave Fiscal.",
                    "comprobantes": [],
                }

            # === STEP 2: Open Mis Comprobantes via search bar ===
            search_input = page.locator("#buscadorInput")
            await search_input.fill("Mis Comprobantes")
            await asyncio.sleep(2)
            await page.locator(".rbt-menu a, .rbt-menu li").first.click()
            await asyncio.sleep(10)

            # The service opens in a new tab/popup
            all_pages = context.pages
            if len(all_pages) < 2:
                await browser.close()
                return {
                    "success": False,
                    "error": "No se pudo abrir Mis Comprobantes",
                    "comprobantes": [],
                }
            mcmp = all_pages[-1]

            # === STEP 3: Select persona ===
            await mcmp.evaluate(
                """(idx) => {
                    document.getElementById('idcontribuyente').value = String(idx);
                    document.seleccionaEmpresaForm.submit();
                }""",
                id_contribuyente,
            )
            await asyncio.sleep(5)

            # === STEP 4: Navigate to the right page ===
            await mcmp.goto(
                f"{MCMP_BASE}/{page_do}",
                wait_until="networkidle",
            )
            await asyncio.sleep(3)

            # === STEP 5: Call the search API ===
            fecha_param = f"{fecha_desde} - {fecha_hasta}"

            # Step 5a: Generate query
            # cuitConsultada must match the CUIT of the selected persona.
            # Extract it from the page text (e.g. "[30-71246122-1]") after
            # persona selection, falling back to the login CUIT.
            actual_cuit = await mcmp.evaluate(
                """() => {
                    const m = document.body.innerText.match(/REPRESENTANDO A:.*?\\[(\\d{2}-\\d{8}-\\d)\\]/);
                    if (m) return m[1].replace(/-/g, '');
                    return '';
                }"""
            ) or cuit_clean
            gen_url = (
                f"{MCMP_BASE}/ajax.do?f=generarConsulta&t={tipo}"
                f"&fechaEmision={urllib.parse.quote(fecha_param)}"
                f"&tiposComprobantes={urllib.parse.quote(tipos_comprobante)}"
                f"&cuitConsultada={actual_cuit}"
            )
            gen_resp_text = await mcmp.evaluate(
                "async (url) => { const r = await fetch(url); return await r.text(); }",
                gen_url,
            )
            gen_data = json.loads(gen_resp_text)

            if gen_data.get("estado") != "ok":
                await browser.close()
                return {
                    "success": False,
                    "error": f"Error al generar consulta: {gen_data}",
                    "comprobantes": [],
                }

            query_id = gen_data["datos"]["idConsulta"]

            # Step 5b: Estimate results (required before fetching)
            est_url = f"{MCMP_BASE}/ajax.do?f=estimarResultados&id={query_id}"
            est_resp_text = await mcmp.evaluate(
                "async (url) => { const r = await fetch(url); return await r.text(); }",
                est_url,
            )
            est_data = json.loads(est_resp_text)
            server_side = est_data.get("datos", {}).get("serverSide", False)

            # Step 5c: Fetch results
            all_comprobantes_raw = []

            if not server_side:
                # Client-side: all data in one call
                list_url = f"{MCMP_BASE}/ajax.do?f=listaResultados&id={query_id}"
                list_resp_text = await mcmp.evaluate(
                    "async (url) => { const r = await fetch(url); return await r.text(); }",
                    list_url,
                )
                list_data = json.loads(list_resp_text)
                all_comprobantes_raw = list_data.get("datos", {}).get("data", [])
            else:
                # Server-side pagination: fetch pages with retry
                start = 0
                page_size = 500
                max_retries = 3
                while True:
                    list_url = (
                        f"{MCMP_BASE}/ajax.do?f=listaResultados&id={query_id}"
                        f"&start={start}&length={page_size}"
                    )
                    list_resp_text = ""
                    for attempt in range(max_retries):
                        list_resp_text = await mcmp.evaluate(
                            "async (url) => { const r = await fetch(url); return await r.text(); }",
                            list_url,
                        )
                        if list_resp_text:
                            break
                        await asyncio.sleep(2 * (attempt + 1))

                    if not list_resp_text:
                        break  # Give up on this page after retries

                    list_data = json.loads(list_resp_text)
                    page_data = list_data.get("datos", {}).get("data", [])
                    all_comprobantes_raw.extend(page_data)
                    if len(page_data) < page_size:
                        break
                    start += page_size
                    await asyncio.sleep(1)  # Rate-limit between pages

            # === STEP 6: Parse into structured dicts ===
            comprobantes = []
            for raw in all_comprobantes_raw:
                try:
                    comprobantes.append(parser(raw))
                except Exception:
                    pass  # Skip malformed records

            await browser.close()

            return {
                "success": True,
                "cuit": cuit_clean,
                "cuit_representado": actual_cuit,
                "fecha_desde": fecha_desde,
                "fecha_hasta": fecha_hasta,
                "total": len(comprobantes),
                "comprobantes": comprobantes,
            }

        except Exception as e:
            try:
                await browser.close()
            except Exception:
                pass
            return {"success": False, "error": str(e), "comprobantes": []}


# ── Public API ────────────────────────────────────────────────────────────────

async def get_comprobantes_recibidos(
    cuit: str,
    password: str,
    fecha_desde: str,
    fecha_hasta: str,
    tipos_comprobante: str = "",
    id_contribuyente: int = 1,
) -> dict[str, Any]:
    """Fetch received comprobantes from ARCA Mis Comprobantes."""
    return await _fetch_comprobantes(
        cuit, password, fecha_desde, fecha_hasta,
        tipo="R",
        tipos_comprobante=tipos_comprobante,
        id_contribuyente=id_contribuyente,
    )


async def get_comprobantes_emitidos(
    cuit: str,
    password: str,
    fecha_desde: str,
    fecha_hasta: str,
    tipos_comprobante: str = "",
    id_contribuyente: int = 1,
) -> dict[str, Any]:
    """Fetch issued comprobantes from ARCA Mis Comprobantes."""
    return await _fetch_comprobantes(
        cuit, password, fecha_desde, fecha_hasta,
        tipo="E",
        tipos_comprobante=tipos_comprobante,
        id_contribuyente=id_contribuyente,
    )
