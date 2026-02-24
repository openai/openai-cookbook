"""
Reconciliation: ARCA Comprobantes Emitidos ↔ Colppy Facturas de Venta.

Matches invoices by CAE (Código de Autorización Electrónica), which is
globally unique per AFIP electronic invoice.

Both sources store amounts in pesos.

Every input record is classified into exactly one bucket:
  matched, amount_mismatch, currency_mismatch, only_arca, only_colppy,
  duplicate_cae, missing_cae

When ARCA data is not cached for the requested date range, the service
automatically fetches it from ARCA using Playwright (scraper), saves to
SQLite cache, and proceeds with the reconciliation.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, AsyncIterator

from backend.services import arca_db, colppy_api
from backend.services.comprobantes_api import get_comprobantes_emitidos

logger = logging.getLogger(__name__)


def _safe_float(raw: str | float | None) -> float:
    """Parse a raw value to float, returning 0.0 on failure."""
    if raw is None:
        return 0.0
    try:
        return round(float(raw), 2)
    except (ValueError, TypeError):
        return 0.0


def _arca_record_summary(c: dict[str, Any]) -> dict[str, Any]:
    """Extract the fields we want to show for an ARCA record."""
    return {
        "numero": c.get("numero", ""),
        "fecha_emision": c.get("fecha_emision", ""),
        "tipo_comprobante": c.get("tipo_comprobante", ""),
        "tipo_comprobante_codigo": c.get("tipo_comprobante_codigo"),
        "punto_venta": c.get("punto_venta"),
        "cuit_contraparte": c.get("cuit_contraparte", ""),
        "tipo_doc_contraparte": c.get("tipo_doc_contraparte", ""),
        "denominacion_contraparte": c.get("denominacion_contraparte", ""),
        "moneda": c.get("moneda", "$"),
        "importe_total": c.get("importe_total", 0.0),
        "cod_autorizacion": c.get("cod_autorizacion", ""),
        # Tax breakdown (from ARCA list API raw array)
        "tipo_cambio": c.get("tipo_cambio"),
        "neto_gravado": c.get("neto_gravado"),
        "neto_no_gravado": c.get("neto_no_gravado"),
        "exento": c.get("exento"),
        "iva_total": c.get("iva_total"),
        "otros_tributos": c.get("otros_tributos"),
    }


_ESTADO_FACTURA = {"3": "Anulada", "5": "Activa", "6": "Aplicada parcial"}


def _colppy_record_summary(v: dict[str, Any]) -> dict[str, Any]:
    """Extract the fields we want to show for a Colppy record."""
    estado_id = str(v.get("idEstadoFactura", ""))
    return {
        "nroFactura": v.get("nroFactura", ""),
        "fechaFactura": v.get("fechaFactura", ""),
        "idTipoComprobante": v.get("idTipoComprobante", ""),
        "RazonSocial": v.get("RazonSocial", ""),
        "totalFactura_pesos": _safe_float(v.get("totalFactura", "0")),
        "cae": v.get("cae", ""),
        "idEstadoFactura": estado_id,
        "estadoFactura": _ESTADO_FACTURA.get(estado_id, estado_id),
        "descripcion": v.get("descripcion", ""),
        # Tax breakdown
        "netoGravado": _safe_float(v.get("netoGravado", "0")),
        "netoNoGravado": _safe_float(v.get("netoNoGravado", "0")),
        "iva21": _safe_float(v.get("IVA21", "0")),
        "iva105": _safe_float(v.get("IVA105", "0")),
        "iva27": _safe_float(v.get("IVA27", "0")),
        "totalIVA": _safe_float(v.get("totalIVA", "0")),
        # Percepciones
        "percepcionIVA": _safe_float(v.get("percepcionIVA", "0")),
        "percepcionIIBB": _safe_float(v.get("percepcionIIBB", "0")),
        # Currency & exchange
        "idMoneda": v.get("idMoneda"),
        "valorCambio": _safe_float(v.get("valorCambio", "0")),
        # Payment
        "fechaPago": v.get("fechaPago", ""),
        "idCondicionPago": v.get("idCondicionPago"),
    }


def _index_by_cae(
    items: list[dict[str, Any]],
    cae_field: str,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Index records by CAE, detecting duplicates and missing CAEs.

    Returns:
      (by_cae, no_cae_records, duplicate_records)

    Every input record ends up in exactly one of these three groups.
    """
    by_cae: dict[str, dict[str, Any]] = {}
    no_cae: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []

    for item in items:
        cae = (item.get(cae_field) or "").strip()
        if not cae:
            no_cae.append(item)
        elif cae in by_cae:
            duplicates.append(item)
        else:
            by_cae[cae] = item

    return by_cae, no_cae, duplicates


async def reconcile_emitidos(
    cuit_representado: str,
    id_empresa: str,
    fecha_desde: str,
    fecha_hasta: str,
) -> dict[str, Any]:
    """
    Cross-reference ARCA emitidos (from SQLite cache) against
    Colppy facturas de venta (fetched live from API).

    Returns structured result with summary counts and discrepancy details.
    """
    # 1. Load ARCA emitidos from SQLite cache
    arca_items, arca_fetched = arca_db.get_comprobantes(
        cuit_representado, "E", fecha_desde, fecha_hasta,
    )

    arca_auto_fetched = False

    # 1b. Auto-fetch from ARCA if cache is empty
    if not arca_items and arca_fetched is None:
        login_cuit = os.getenv("ARCA_CUIT", "").strip()
        login_password = os.getenv("ARCA_PASSWORD", "").strip()

        if not login_cuit or not login_password:
            return {
                "success": False,
                "message": (
                    f"No hay datos ARCA en caché para {fecha_desde} – {fecha_hasta} "
                    "y no se puede descargar automáticamente: "
                    "configure ARCA_CUIT y ARCA_PASSWORD en .env"
                ),
            }

        # Convert YYYY-MM-DD → DD/MM/YYYY for the scraper
        try:
            d_desde = datetime.strptime(fecha_desde, "%Y-%m-%d").strftime("%d/%m/%Y")
            d_hasta = datetime.strptime(fecha_hasta, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return {
                "success": False,
                "message": f"Formato de fecha inválido: {fecha_desde} / {fecha_hasta} (esperado YYYY-MM-DD)",
            }

        id_contribuyente = int(os.getenv("ARCA_ENTITY_INDEX", "0"))

        logger.info(
            "ARCA cache empty for %s [%s – %s]. Auto-fetching from ARCA (entity %d)...",
            cuit_representado, fecha_desde, fecha_hasta, id_contribuyente,
        )

        try:
            scrape_result = await get_comprobantes_emitidos(
                cuit=login_cuit,
                password=login_password,
                fecha_desde=d_desde,
                fecha_hasta=d_hasta,
                id_contribuyente=id_contribuyente,
            )
        except Exception as e:
            logger.error("ARCA auto-fetch failed: %s", e)
            return {
                "success": False,
                "message": f"No hay datos ARCA en caché y la descarga automática falló: {e}",
            }

        if not scrape_result.get("success"):
            return {
                "success": False,
                "message": (
                    f"No hay datos ARCA en caché y la descarga automática falló: "
                    f"{scrape_result.get('error', 'unknown error')}"
                ),
            }

        # Save to SQLite cache
        scraped_items = scrape_result.get("comprobantes", [])
        cuit_repr = scrape_result.get("cuit_representado") or cuit_representado
        if scraped_items:
            arca_db.save_comprobantes(cuit_repr, scraped_items, direccion="E")
            logger.info(
                "ARCA auto-fetch: saved %d comprobantes for %s",
                len(scraped_items), cuit_repr,
            )

        # Re-read from cache (ensures consistent format with normal path)
        arca_items, arca_fetched = arca_db.get_comprobantes(
            cuit_representado, "E", fecha_desde, fecha_hasta,
        )
        arca_auto_fetched = True

        if not arca_items:
            return {
                "success": False,
                "message": (
                    f"Se descargaron {len(scraped_items)} comprobantes de ARCA pero "
                    f"ninguno corresponde al rango {fecha_desde} – {fecha_hasta} "
                    f"para CUIT {cuit_representado}."
                ),
            }

    # 2. Fetch Colppy ventas via API
    try:
        login_result = await colppy_api.login()
        if not login_result or not login_result.get("success"):
            msg = (login_result or {}).get("message", "unknown error")
            return {"success": False, "message": f"Colppy login failed: {msg}"}

        clave = login_result["data"]["claveSesion"]
        try:
            colppy_result = await colppy_api.list_comprobantes_venta(
                clave, id_empresa, fecha_desde, fecha_hasta,
            )
        finally:
            await colppy_api.logout(clave)

        if not colppy_result["success"]:
            return {
                "success": False,
                "message": f"Colppy list_comprobantes_venta failed: {colppy_result.get('message', '')}",
            }
    except Exception as e:
        return {"success": False, "message": f"Colppy API error: {e}"}

    colppy_items = colppy_result["data"] or []

    # 3. Index both sides by CAE — detecting duplicates and missing CAEs
    arca_by_cae, arca_no_cae, arca_dup_cae = _index_by_cae(arca_items, "cod_autorizacion")
    colppy_by_cae, colppy_no_cae, colppy_dup_cae = _index_by_cae(colppy_items, "cae")

    # 4. Build discrepancies list — every record must land in a bucket
    discrepancies: list[dict[str, Any]] = []

    # 4a. Records with no CAE
    for item in arca_no_cae:
        discrepancies.append({
            "status": "missing_cae",
            "source": "arca",
            "arca": _arca_record_summary(item),
            "colppy": None,
        })
    for item in colppy_no_cae:
        discrepancies.append({
            "status": "missing_cae",
            "source": "colppy",
            "arca": None,
            "colppy": _colppy_record_summary(item),
        })

    # 4b. Records with duplicate CAE (2nd+ occurrence of same CAE)
    for item in arca_dup_cae:
        discrepancies.append({
            "status": "duplicate_cae",
            "source": "arca",
            "arca": _arca_record_summary(item),
            "colppy": None,
        })
    for item in colppy_dup_cae:
        discrepancies.append({
            "status": "duplicate_cae",
            "source": "colppy",
            "arca": None,
            "colppy": _colppy_record_summary(item),
        })

    # 4c. Cross-match unique CAEs
    matched = 0
    matched_pairs = []
    amount_mismatch = 0
    currency_mismatch = 0

    all_caes = set(arca_by_cae.keys()) | set(colppy_by_cae.keys())

    colppy_total_pesos = 0.0
    arca_total_pesos = 0.0

    for cae in sorted(all_caes):
        in_arca = cae in arca_by_cae
        in_colppy = cae in colppy_by_cae

        if in_colppy:
            colppy_total_pesos += _safe_float(colppy_by_cae[cae].get("totalFactura", "0"))
        if in_arca:
            arca_total_pesos += _safe_float(arca_by_cae[cae].get("importe_total", 0))

        if in_arca and in_colppy:
            arca_rec = arca_by_cae[cae]
            arca_moneda = (arca_rec.get("moneda") or "$").strip()
            arca_amount = _safe_float(arca_rec.get("importe_total", 0))
            colppy_amt = _safe_float(colppy_by_cae[cae].get("totalFactura", "0"))

            if arca_moneda != "$":
                # Foreign currency: ARCA stores in original currency, Colppy in ARS.
                # CAE match proves it's the same invoice — count as matched.
                currency_mismatch += 1
                matched += 1
                matched_pairs.append({
                    "arca": _arca_record_summary(arca_rec),
                    "colppy": _colppy_record_summary(colppy_by_cae[cae]),
                    "foreign_currency": arca_moneda,
                })
            elif abs(arca_amount - colppy_amt) < 0.02:
                matched += 1
                matched_pairs.append({
                    "arca": _arca_record_summary(arca_rec),
                    "colppy": _colppy_record_summary(colppy_by_cae[cae]),
                })
            else:
                amount_mismatch += 1
                discrepancies.append({
                    "status": "amount_mismatch",
                    "arca": _arca_record_summary(arca_rec),
                    "colppy": _colppy_record_summary(colppy_by_cae[cae]),
                    "diff_pesos": round(arca_amount - colppy_amt, 2),
                })

        elif in_arca and not in_colppy:
            discrepancies.append({
                "status": "only_arca",
                "arca": _arca_record_summary(arca_by_cae[cae]),
                "colppy": None,
            })

        elif in_colppy and not in_arca:
            discrepancies.append({
                "status": "only_colppy",
                "arca": None,
                "colppy": _colppy_record_summary(colppy_by_cae[cae]),
            })

    only_arca = sum(1 for d in discrepancies if d["status"] == "only_arca")
    only_colppy = sum(1 for d in discrepancies if d["status"] == "only_colppy")

    # Count Colppy anuladas (idEstadoFactura == "3") for data quality warnings
    colppy_anuladas = sum(
        1 for v in colppy_items if str(v.get("idEstadoFactura", "")) == "3"
    )

    return {
        "success": True,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "reconciled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "arca_total": len(arca_items),
            "colppy_total": len(colppy_items),
            "matched": matched,
            "amount_mismatch": amount_mismatch,
            "currency_mismatch": currency_mismatch,
            "only_arca": only_arca,
            "only_colppy": only_colppy,
            "arca_no_cae": len(arca_no_cae),
            "colppy_no_cae": len(colppy_no_cae),
            "arca_duplicate_cae": len(arca_dup_cae),
            "colppy_duplicate_cae": len(colppy_dup_cae),
            "arca_importe_total": round(arca_total_pesos, 2),
            "colppy_importe_total": round(colppy_total_pesos, 2),
            "colppy_anuladas": colppy_anuladas,
        },
        "arca_fetched_at": arca_fetched,
        "arca_auto_fetched": arca_auto_fetched,
        "discrepancies": discrepancies,
        "matched_pairs": matched_pairs,
    }


_MONTH_NAMES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def _month_ranges(fecha_desde: str, fecha_hasta: str) -> list[tuple[str, str, str]]:
    """
    Split a date range into per-month chunks.
    Returns list of (month_label, from_date, to_date).
    E.g. ("noviembre 2025", "2025-11-01", "2025-11-30")
    """
    from calendar import monthrange
    start = datetime.strptime(fecha_desde, "%Y-%m-%d").date()
    end = datetime.strptime(fecha_hasta, "%Y-%m-%d").date()
    ranges = []
    cur = start.replace(day=1)
    while cur <= end:
        m_start = max(cur, start)
        last_day = monthrange(cur.year, cur.month)[1]
        m_end = min(cur.replace(day=last_day), end)
        label = f"{_MONTH_NAMES_ES[cur.month]} {cur.year}"
        ranges.append((label, m_start.strftime("%Y-%m-%d"), m_end.strftime("%Y-%m-%d")))
        # Advance to next month
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return ranges


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def reconcile_emitidos_stream(
    cuit_representado: str,
    id_empresa: str,
    fecha_desde: str,
    fecha_hasta: str,
) -> AsyncIterator[str]:
    """
    Same as reconcile_emitidos but yields SSE progress events, then the final result.

    Events:
      {"type":"progress", "step":1, "total":5, "message":"...", "pct":20}
      {"type":"result", ...}   (the full reconciliation JSON)
      {"type":"error", "message":"..."}
    """
    total_steps = 5

    # --- Step 1: ARCA cache lookup ---
    yield _sse({"type": "progress", "step": 1, "total": total_steps, "pct": 10,
                "message": "Cargando comprobantes ARCA del caché..."})

    arca_items, arca_fetched = arca_db.get_comprobantes(
        cuit_representado, "E", fecha_desde, fecha_hasta,
    )
    arca_auto_fetched = False

    if not arca_items and arca_fetched is None:
        # Need to auto-fetch from ARCA
        login_cuit = os.getenv("ARCA_CUIT", "").strip()
        login_password = os.getenv("ARCA_PASSWORD", "").strip()

        if not login_cuit or not login_password:
            yield _sse({"type": "error", "message":
                f"No hay datos ARCA en caché para {fecha_desde} – {fecha_hasta} "
                "y no se puede descargar: configure ARCA_CUIT y ARCA_PASSWORD en .env"})
            return

        yield _sse({"type": "progress", "step": 1, "total": total_steps, "pct": 15,
                    "message": "Descargando comprobantes de ARCA (puede tomar ~2 min)..."})

        try:
            d_desde = datetime.strptime(fecha_desde, "%Y-%m-%d").strftime("%d/%m/%Y")
            d_hasta = datetime.strptime(fecha_hasta, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            yield _sse({"type": "error", "message": f"Formato de fecha inválido: {fecha_desde} / {fecha_hasta}"})
            return

        id_contribuyente = int(os.getenv("ARCA_ENTITY_INDEX", "0"))

        try:
            scrape_result = await get_comprobantes_emitidos(
                cuit=login_cuit, password=login_password,
                fecha_desde=d_desde, fecha_hasta=d_hasta,
                id_contribuyente=id_contribuyente,
            )
        except Exception as e:
            yield _sse({"type": "error", "message": f"Descarga ARCA falló: {e}"})
            return

        if not scrape_result.get("success"):
            yield _sse({"type": "error", "message":
                f"Descarga ARCA falló: {scrape_result.get('error', 'unknown error')}"})
            return

        scraped_items = scrape_result.get("comprobantes", [])
        cuit_repr = scrape_result.get("cuit_representado") or cuit_representado
        if scraped_items:
            arca_db.save_comprobantes(cuit_repr, scraped_items, direccion="E")

        arca_items, arca_fetched = arca_db.get_comprobantes(
            cuit_representado, "E", fecha_desde, fecha_hasta,
        )
        arca_auto_fetched = True

        if not arca_items:
            yield _sse({"type": "error", "message":
                f"Se descargaron {len(scraped_items)} comprobantes pero ninguno en el rango solicitado."})
            return

    yield _sse({"type": "progress", "step": 1, "total": total_steps, "pct": 20,
                "message": f"ARCA: {len(arca_items)} comprobantes cargados"})

    # --- Step 2: Colppy login ---
    yield _sse({"type": "progress", "step": 2, "total": total_steps, "pct": 25,
                "message": "Conectando con Colppy..."})

    try:
        login_result = await colppy_api.login()
        if not login_result or not login_result.get("success"):
            msg = (login_result or {}).get("message", "unknown error")
            yield _sse({"type": "error", "message": f"Colppy login falló: {msg}"})
            return
        clave = login_result["data"]["claveSesion"]
    except Exception as e:
        yield _sse({"type": "error", "message": f"Colppy login error: {e}"})
        return

    # --- Step 3: Colppy fetch ventas (month by month) ---
    months = _month_ranges(fecha_desde, fecha_hasta)
    colppy_items: list[dict] = []
    # Progress range: 30% → 70% spread across months
    pct_start, pct_end = 30, 70

    try:
        try:
            for idx, (month_label, m_desde, m_hasta) in enumerate(months):
                pct = pct_start + int((pct_end - pct_start) * idx / max(len(months), 1))
                yield _sse({"type": "progress", "step": 3, "total": total_steps, "pct": pct,
                            "message": f"Descargando facturas de {month_label}..."})

                month_result = await colppy_api.list_comprobantes_venta(
                    clave, id_empresa, m_desde, m_hasta,
                )
                if not month_result["success"]:
                    yield _sse({"type": "error", "message":
                        f"Colppy ventas falló ({month_label}): {month_result.get('message', '')}"})
                    return

                month_items = month_result["data"] or []
                colppy_items.extend(month_items)

                pct_done = pct_start + int((pct_end - pct_start) * (idx + 1) / len(months))
                yield _sse({"type": "progress", "step": 3, "total": total_steps, "pct": pct_done,
                            "message": f"{month_label.capitalize()}: {len(month_items)} facturas — total: {len(colppy_items)}"})
        finally:
            await colppy_api.logout(clave)
    except Exception as e:
        yield _sse({"type": "error", "message": f"Colppy API error: {e}"})
        return

    # --- Step 4: Index by CAE ---
    yield _sse({"type": "progress", "step": 4, "total": total_steps, "pct": 80,
                "message": f"Indexando {len(arca_items) + len(colppy_items)} comprobantes por CAE..."})

    arca_by_cae, arca_no_cae, arca_dup_cae = _index_by_cae(arca_items, "cod_autorizacion")
    colppy_by_cae, colppy_no_cae, colppy_dup_cae = _index_by_cae(colppy_items, "cae")

    # --- Step 5: Cross-match ---
    yield _sse({"type": "progress", "step": 5, "total": total_steps, "pct": 90,
                "message": "Comparando facturas y detectando discrepancias..."})

    discrepancies: list[dict[str, Any]] = []

    for item in arca_no_cae:
        discrepancies.append({"status": "missing_cae", "source": "arca",
                              "arca": _arca_record_summary(item), "colppy": None})
    for item in colppy_no_cae:
        discrepancies.append({"status": "missing_cae", "source": "colppy",
                              "arca": None, "colppy": _colppy_record_summary(item)})
    for item in arca_dup_cae:
        discrepancies.append({"status": "duplicate_cae", "source": "arca",
                              "arca": _arca_record_summary(item), "colppy": None})
    for item in colppy_dup_cae:
        discrepancies.append({"status": "duplicate_cae", "source": "colppy",
                              "arca": None, "colppy": _colppy_record_summary(item)})

    matched = 0
    matched_pairs = []
    amount_mismatch = 0
    currency_mismatch = 0
    colppy_total_pesos = 0.0
    arca_total_pesos = 0.0

    all_caes = set(arca_by_cae.keys()) | set(colppy_by_cae.keys())

    for cae in sorted(all_caes):
        in_arca = cae in arca_by_cae
        in_colppy = cae in colppy_by_cae

        if in_colppy:
            colppy_total_pesos += _safe_float(colppy_by_cae[cae].get("totalFactura", "0"))
        if in_arca:
            arca_total_pesos += _safe_float(arca_by_cae[cae].get("importe_total", 0))

        if in_arca and in_colppy:
            arca_rec = arca_by_cae[cae]
            arca_moneda = (arca_rec.get("moneda") or "$").strip()
            arca_amount = _safe_float(arca_rec.get("importe_total", 0))
            colppy_amt = _safe_float(colppy_by_cae[cae].get("totalFactura", "0"))

            if arca_moneda != "$":
                currency_mismatch += 1
                matched += 1
                matched_pairs.append({
                    "arca": _arca_record_summary(arca_rec),
                    "colppy": _colppy_record_summary(colppy_by_cae[cae]),
                    "foreign_currency": arca_moneda,
                })
            elif abs(arca_amount - colppy_amt) < 0.02:
                matched += 1
                matched_pairs.append({
                    "arca": _arca_record_summary(arca_rec),
                    "colppy": _colppy_record_summary(colppy_by_cae[cae]),
                })
            else:
                amount_mismatch += 1
                discrepancies.append({
                    "status": "amount_mismatch",
                    "arca": _arca_record_summary(arca_rec),
                    "colppy": _colppy_record_summary(colppy_by_cae[cae]),
                    "diff_pesos": round(arca_amount - colppy_amt, 2),
                })
        elif in_arca and not in_colppy:
            discrepancies.append({
                "status": "only_arca",
                "arca": _arca_record_summary(arca_by_cae[cae]),
                "colppy": None,
            })
        elif in_colppy and not in_arca:
            discrepancies.append({
                "status": "only_colppy",
                "arca": None,
                "colppy": _colppy_record_summary(colppy_by_cae[cae]),
            })

    only_arca = sum(1 for d in discrepancies if d["status"] == "only_arca")
    only_colppy = sum(1 for d in discrepancies if d["status"] == "only_colppy")

    # --- Done: yield final result ---
    yield _sse({"type": "progress", "step": 5, "total": total_steps, "pct": 100,
                "message": f"Listo — {matched} matcheados, {len(discrepancies)} discrepancias"})

    colppy_anuladas_stream = sum(
        1 for v in colppy_items if str(v.get("idEstadoFactura", "")) == "3"
    )

    yield _sse({"type": "result", "data": {
        "success": True,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "reconciled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "arca_total": len(arca_items),
            "colppy_total": len(colppy_items),
            "matched": matched,
            "amount_mismatch": amount_mismatch,
            "currency_mismatch": currency_mismatch,
            "only_arca": only_arca,
            "only_colppy": only_colppy,
            "arca_no_cae": len(arca_no_cae),
            "colppy_no_cae": len(colppy_no_cae),
            "arca_duplicate_cae": len(arca_dup_cae),
            "colppy_duplicate_cae": len(colppy_dup_cae),
            "arca_importe_total": round(arca_total_pesos, 2),
            "colppy_importe_total": round(colppy_total_pesos, 2),
            "colppy_anuladas": colppy_anuladas_stream,
        },
        "arca_fetched_at": arca_fetched,
        "arca_auto_fetched": arca_auto_fetched,
        "discrepancies": discrepancies,
        "matched_pairs": matched_pairs,
    }})
