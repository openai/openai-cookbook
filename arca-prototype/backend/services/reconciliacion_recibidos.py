"""
Reconciliation: ARCA Comprobantes Recibidos ↔ Colppy Facturas de Compra.

Matches purchase invoices by invoice number (PPPPP-NNNNNNNN format),
which is consistent across both sources.

Colppy purchase invoices don't have CAE or CUIT — only idProveedor.
We resolve idProveedor → CUIT via the proveedores list, enabling
CUIT validation and retenciones overlay.

Every input record is classified into exactly one bucket:
  matched, amount_mismatch, only_arca, only_colppy

Additional layers:
  - Percepciones comparison: ARCA otros_tributos vs Colppy percepcionIVA+IIBB
  - Retenciones overlay: linked ARCA retenciones by supplier CUIT + period
"""

import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, AsyncIterator

from backend.services import arca_db, colppy_api
from backend.services.comprobantes_api import TIPO_COMPROBANTE, get_comprobantes_recibidos

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_float(raw: str | float | None) -> float:
    """Parse a raw value to float, returning 0.0 on failure."""
    if raw is None:
        return 0.0
    try:
        return round(float(raw), 2)
    except (ValueError, TypeError):
        return 0.0


def _normalize_cuit(cuit: str) -> str:
    """Strip dashes/spaces from CUIT: '30-65485516-8' → '30654855168'."""
    return re.sub(r"[^0-9]", "", str(cuit or ""))


def _normalize_invoice_number(nro: str) -> str:
    """
    Normalize invoice number to comparable form.
    Both sources use PPPPP-NNNNNNNN format, but minor formatting
    differences (leading zeros, spaces) may exist.
    """
    nro = (nro or "").strip()
    # Already in PPPPP-NNNNNNNN format — just normalize
    return nro


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


_ESTADO_FACTURA = {"3": "Anulada", "5": "Activa", "6": "Aplicada parcial"}


# ── Record summaries ─────────────────────────────────────────────────────────

def _arca_record_summary(c: dict[str, Any]) -> dict[str, Any]:
    """Extract fields we want to show for an ARCA recibido record."""
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
        # Tax breakdown
        "tipo_cambio": c.get("tipo_cambio"),
        "neto_gravado": c.get("neto_gravado"),
        "neto_no_gravado": c.get("neto_no_gravado"),
        "exento": c.get("exento"),
        "iva_total": c.get("iva_total"),
        "otros_tributos": c.get("otros_tributos"),
    }


def _colppy_record_summary(v: dict[str, Any], cuit_map: dict[int, str]) -> dict[str, Any]:
    """Extract fields we want to show for a Colppy compra record."""
    estado_id = str(v.get("idEstadoFactura", ""))
    id_prov = v.get("idProveedor")
    cuit_proveedor = cuit_map.get(id_prov, "")
    # Percepciones total
    perc_iva = _safe_float(v.get("percepcionIVA", "0"))
    perc_iibb = _safe_float(v.get("percepcionIIBB", "0"))
    perc_iibb1 = _safe_float(v.get("percepcionIIBB1", "0"))
    perc_iibb2 = _safe_float(v.get("percepcionIIBB2", "0"))
    iibb_local = _safe_float(v.get("IIBBLocal", "0"))
    iibb_otro = _safe_float(v.get("IIBBOtro", "0"))
    total_percepciones = round(perc_iva + perc_iibb + perc_iibb1 + perc_iibb2 + iibb_local + iibb_otro, 2)

    return {
        "nroFactura": v.get("nroFactura", ""),
        "fechaFactura": v.get("fechaFactura", ""),
        "idTipoComprobante": v.get("idTipoComprobante", ""),
        "tipo_comprobante": TIPO_COMPROBANTE.get(str(v.get("idTipoComprobante", "")), f"Tipo {v.get('idTipoComprobante', '')}"),
        "RazonSocial": v.get("RazonSocial", ""),
        "idEstadoFactura": estado_id,
        "estadoFactura": _ESTADO_FACTURA.get(estado_id, estado_id),
        "totalFactura_pesos": _safe_float(v.get("totalFactura", "0")),
        "cuit_proveedor": cuit_proveedor,
        "idProveedor": id_prov,
        # Tax breakdown
        "netoGravado": _safe_float(v.get("netoGravado", "0")),
        "netoNoGravado": _safe_float(v.get("netoNoGravado", "0")),
        "iva21": _safe_float(v.get("IVA21", "0")),
        "iva105": _safe_float(v.get("IVA105", "0")),
        "iva27": _safe_float(v.get("IVA27", "0")),
        "totalIVA": _safe_float(v.get("totalIVA", "0")),
        # Percepciones
        "percepcionIVA": perc_iva,
        "percepcionIIBB": perc_iibb,
        "percepcionIIBB1": perc_iibb1,
        "percepcionIIBB2": perc_iibb2,
        "IIBBLocal": iibb_local,
        "IIBBOtro": iibb_otro,
        "totalPercepciones": total_percepciones,
        # Ganancias regime
        "idRetGanancias": v.get("idRetGanancias"),
        # Currency & payment
        "idMoneda": v.get("idMoneda"),
        "valorCambio": _safe_float(v.get("valorCambio", "0")),
        "fechaPago": v.get("fechaPago", ""),
        "idCondicionPago": v.get("idCondicionPago"),
    }


# ── Indexing ─────────────────────────────────────────────────────────────────

def _index_by_invoice_number(
    items: list[dict[str, Any]],
    number_field: str,
    cuit_extractor=None,
    tipo_extractor=None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Index records by compound key (supplier_cuit|tipo|invoice_number).

    In Argentina, invoice numbers are only unique within (CUIT emisor +
    tipo comprobante + punto de venta).  Two different suppliers can both
    issue ``00001-00000003``, and the *same* supplier can issue a Factura
    and a Nota de Crédito with the same number.

    When *cuit_extractor* and/or *tipo_extractor* are provided, they are
    included in the dict key to avoid false-positive duplicate detection.

    Returns (by_key, no_number, duplicates).
    """
    by_key: dict[str, dict[str, Any]] = {}
    no_number: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []

    for item in items:
        nro = _normalize_invoice_number(item.get(number_field, ""))
        if not nro:
            no_number.append(item)
            continue

        parts = []
        if cuit_extractor:
            parts.append(cuit_extractor(item) or "")
        if tipo_extractor:
            parts.append(str(tipo_extractor(item) or ""))
        if parts:
            key = "|".join(parts) + "|" + nro
        else:
            key = nro

        if key in by_key:
            item["_duplicate_of_number"] = nro
            duplicates.append(item)
        else:
            by_key[key] = item

    return by_key, no_number, duplicates


def _extract_nro_from_key(key: str) -> str:
    """Extract the invoice number part from a compound key ``cuit|tipo|nro``."""
    return key.rsplit("|", 1)[-1] if "|" in key else key


# ── Retenciones overlay ──────────────────────────────────────────────────────

def _build_retenciones_index(
    cuit_representado: str,
    fecha_desde: str,
    fecha_hasta: str,
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """
    Load cached ARCA retenciones and index by (agent_cuit, YYYY-MM).
    Returns empty dict if no retenciones cached.
    """
    retenciones, _ = arca_db.get_retenciones(cuit_representado, fecha_desde, fecha_hasta)
    if not retenciones:
        return {}

    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in retenciones:
        agent_cuit = _normalize_cuit(r.get("cuitAgenteRetencion", ""))
        fecha = (r.get("fechaRetencion") or "")[:10]
        periodo = fecha[:7]  # YYYY-MM
        if agent_cuit and periodo:
            index[(agent_cuit, periodo)].append({
                "numeroCertificado": r.get("numeroCertificado", ""),
                "fechaRetencion": fecha,
                "importeRetenido": _safe_float(r.get("importeRetenido", 0)),
                "impuestoRetenido": r.get("impuestoRetenido", ""),
                "codigoRegimen": r.get("codigoRegimen", ""),
                "descripcionOperacion": r.get("descripcionOperacion", ""),
            })
    return index


def _get_linked_retenciones(
    ret_index: dict[tuple[str, str], list[dict]],
    supplier_cuit: str,
    fecha: str,
) -> list[dict[str, Any]]:
    """Find retenciones for a supplier CUIT in the same month as the invoice."""
    periodo = (fecha or "")[:7]
    cuit = _normalize_cuit(supplier_cuit)
    if not cuit or not periodo:
        return []
    return ret_index.get((cuit, periodo), [])


# ── Month ranges (for progress) ─────────────────────────────────────────────

_MONTH_NAMES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def _month_ranges(fecha_desde: str, fecha_hasta: str) -> list[tuple[str, str, str]]:
    """Split a date range into per-month chunks."""
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
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return ranges


# ── SSE Stream reconciliation ────────────────────────────────────────────────

async def reconcile_recibidos_stream(
    cuit_representado: str,
    id_empresa: str,
    fecha_desde: str,
    fecha_hasta: str,
) -> AsyncIterator[str]:
    """
    Reconcile ARCA comprobantes recibidos vs Colppy facturas de compra.
    Yields SSE progress events, then the final result.

    Steps:
      1. Load ARCA comprobantes recibidos from cache (auto-fetch if empty)
      2. Colppy login
      3. Fetch Colppy proveedores → build CUIT map
      4. Fetch Colppy compras month-by-month
      5. Index + cross-match + percepciones comparison
      6. Retenciones overlay + final result
    """
    total_steps = 6
    CACHE_MAX_AGE_HOURS = 4  # Re-fetch from ARCA if cache is older than this

    # --- Step 1: ARCA data (cache-first, auto-refresh if stale) ---
    yield _sse({"type": "progress", "step": 1, "total": total_steps, "pct": 5,
                "message": "Cargando comprobantes recibidos ARCA..."})

    arca_items, arca_fetched = arca_db.get_comprobantes(
        cuit_representado, "R", fecha_desde, fecha_hasta,
    )
    arca_auto_fetched = False

    # Determine if we need to fetch from ARCA
    need_fetch = False
    if not arca_items:
        need_fetch = True  # No cache at all
    elif arca_fetched:
        try:
            fetched_dt = datetime.fromisoformat(arca_fetched.replace("Z", "+00:00"))
            from datetime import timezone
            age_hours = (datetime.now(timezone.utc) - fetched_dt).total_seconds() / 3600
            if age_hours > CACHE_MAX_AGE_HOURS:
                need_fetch = True
                logger.info("ARCA cache is %.1f hours old (max %d), refreshing...",
                            age_hours, CACHE_MAX_AGE_HOURS)
        except (ValueError, TypeError):
            need_fetch = True  # Can't parse fetched_at — refresh

    login_cuit = os.getenv("ARCA_CUIT", "").strip()
    login_password = os.getenv("ARCA_PASSWORD", "").strip()

    if need_fetch and login_cuit and login_password:
        yield _sse({"type": "progress", "step": 1, "total": total_steps, "pct": 8,
                    "message": "Descargando comprobantes recibidos de ARCA..."})

        try:
            d_desde = datetime.strptime(fecha_desde, "%Y-%m-%d").strftime("%d/%m/%Y")
            d_hasta = datetime.strptime(fecha_hasta, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            yield _sse({"type": "error", "message": f"Formato de fecha inválido: {fecha_desde} / {fecha_hasta}"})
            return

        id_contribuyente = int(os.getenv("ARCA_ENTITY_INDEX", "0"))

        try:
            scrape_result = await get_comprobantes_recibidos(
                cuit=login_cuit, password=login_password,
                fecha_desde=d_desde, fecha_hasta=d_hasta,
                id_contribuyente=id_contribuyente,
            )
            if scrape_result.get("success"):
                scraped_items = scrape_result.get("comprobantes", [])
                cuit_repr = scrape_result.get("cuit_representado") or cuit_representado
                if scraped_items:
                    arca_db.save_comprobantes(cuit_repr, scraped_items, direccion="R")
                arca_auto_fetched = True
                yield _sse({"type": "progress", "step": 1, "total": total_steps, "pct": 12,
                            "message": f"ARCA: {len(scraped_items)} comprobantes descargados"})
            else:
                logger.warning("ARCA scrape non-success, using cache: %s",
                               scrape_result.get("error", "unknown"))
        except Exception as e:
            logger.warning("ARCA scrape failed, using cache: %s", e)

        # Re-read from cache (freshly updated)
        arca_items, arca_fetched = arca_db.get_comprobantes(
            cuit_representado, "R", fecha_desde, fecha_hasta,
        )
    elif need_fetch and (not login_cuit or not login_password) and not arca_items:
        yield _sse({"type": "error", "message":
            f"No hay datos ARCA recibidos en caché para {fecha_desde} – {fecha_hasta}. "
            "Configure ARCA_CUIT y ARCA_PASSWORD en .env para descarga automática."})
        return

    if not arca_items:
        yield _sse({"type": "error", "message":
            "No se encontraron comprobantes recibidos en ARCA para el rango solicitado."})
        return

    yield _sse({"type": "progress", "step": 1, "total": total_steps, "pct": 15,
                "message": f"ARCA: {len(arca_items)} comprobantes recibidos cargados"})

    # --- Step 2: Colppy login ---
    yield _sse({"type": "progress", "step": 2, "total": total_steps, "pct": 20,
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

    try:
        # --- Step 3: Fetch proveedores → build CUIT map ---
        yield _sse({"type": "progress", "step": 3, "total": total_steps, "pct": 25,
                    "message": "Descargando proveedores de Colppy..."})

        try:
            prov_result = await colppy_api.list_proveedores(clave, id_empresa, only_active=False)
            if not prov_result["success"]:
                yield _sse({"type": "error", "message":
                    f"Colppy proveedores falló: {prov_result.get('message', '')}"})
                return
            proveedores = prov_result["data"] or []
        except Exception as e:
            yield _sse({"type": "error", "message": f"Colppy proveedores error: {e}"})
            return

        # Build idProveedor → normalized CUIT map
        cuit_map: dict[int, str] = {}
        nombre_map: dict[int, str] = {}
        for p in proveedores:
            pid = p.get("idProveedor")
            if pid is not None:
                cuit_map[pid] = _normalize_cuit(p.get("CUIT", ""))
                nombre_map[pid] = p.get("RazonSocial", "")

        yield _sse({"type": "progress", "step": 3, "total": total_steps, "pct": 30,
                    "message": f"Colppy: {len(proveedores)} proveedores cargados"})

        # --- Step 4: Fetch Colppy compras month-by-month ---
        months = _month_ranges(fecha_desde, fecha_hasta)
        colppy_items: list[dict] = []
        pct_start, pct_end = 35, 65

        try:
            for idx, (month_label, m_desde, m_hasta) in enumerate(months):
                pct = pct_start + int((pct_end - pct_start) * idx / max(len(months), 1))
                yield _sse({"type": "progress", "step": 4, "total": total_steps, "pct": pct,
                            "message": f"Descargando facturas de compra de {month_label}..."})

                month_result = await colppy_api.list_comprobantes_compra(
                    clave, id_empresa, m_desde, m_hasta,
                )
                if not month_result["success"]:
                    yield _sse({"type": "error", "message":
                        f"Colppy compras falló ({month_label}): {month_result.get('message', '')}"})
                    return

                month_items = month_result["data"] or []
                colppy_items.extend(month_items)

                pct_done = pct_start + int((pct_end - pct_start) * (idx + 1) / len(months))
                yield _sse({"type": "progress", "step": 4, "total": total_steps, "pct": pct_done,
                            "message": f"{month_label.capitalize()}: {len(month_items)} facturas — total: {len(colppy_items)}"})
        except Exception as e:
            yield _sse({"type": "error", "message": f"Colppy compras error: {e}"})
            return
    finally:
        await colppy_api.logout(clave)

    # --- Step 5: Index + cross-match ---
    yield _sse({"type": "progress", "step": 5, "total": total_steps, "pct": 70,
                "message": f"Indexando {len(arca_items) + len(colppy_items)} comprobantes por proveedor + número..."})

    # Index by compound key (supplier_cuit|invoice_number) to avoid
    # false-positive duplicates when different suppliers share the same nro.
    arca_by_key, arca_no_nro, arca_dup = _index_by_invoice_number(
        arca_items, "numero",
        cuit_extractor=lambda item: _normalize_cuit(item.get("cuit_contraparte", "")),
        tipo_extractor=lambda item: item.get("tipo_comprobante_codigo", ""),
    )
    colppy_by_key, colppy_no_nro, colppy_dup = _index_by_invoice_number(
        colppy_items, "nroFactura",
        cuit_extractor=lambda item: _normalize_cuit(cuit_map.get(item.get("idProveedor"), "")),
        tipo_extractor=lambda item: item.get("idTipoComprobante", ""),
    )

    yield _sse({"type": "progress", "step": 5, "total": total_steps, "pct": 75,
                "message": "Comparando facturas y detectando discrepancias..."})

    discrepancies: list[dict[str, Any]] = []

    # Records with no invoice number
    for item in arca_no_nro:
        discrepancies.append({"status": "missing_number", "source": "arca",
                              "arca": _arca_record_summary(item), "colppy": None})
    for item in colppy_no_nro:
        discrepancies.append({"status": "missing_number", "source": "colppy",
                              "arca": None, "colppy": _colppy_record_summary(item, cuit_map)})

    # True duplicates: same supplier + same invoice number within one source
    for item in arca_dup:
        dup_nro = item.get("_duplicate_of_number", "")
        discrepancies.append({
            "status": "duplicate_number", "source": "arca",
            "duplicate_number": dup_nro,
            "arca": _arca_record_summary(item), "colppy": None,
        })
    for item in colppy_dup:
        dup_nro = item.get("_duplicate_of_number", "")
        discrepancies.append({
            "status": "duplicate_number", "source": "colppy",
            "duplicate_number": dup_nro,
            "arca": None, "colppy": _colppy_record_summary(item, cuit_map),
        })

    # ── Primary cross-match by compound key ──
    matched = 0
    matched_pairs: list[dict[str, Any]] = []
    amount_mismatch = 0
    colppy_total_pesos = 0.0
    arca_total_pesos = 0.0
    matched_keys: set[str] = set()

    all_keys = set(arca_by_key.keys()) | set(colppy_by_key.keys())

    for key in sorted(all_keys):
        in_arca = key in arca_by_key
        in_colppy = key in colppy_by_key

        if in_colppy:
            colppy_total_pesos += _safe_float(colppy_by_key[key].get("totalFactura", "0"))
        if in_arca:
            arca_total_pesos += _safe_float(arca_by_key[key].get("importe_total", 0))

        if in_arca and in_colppy:
            matched_keys.add(key)
            arca_rec = arca_by_key[key]
            colppy_rec = colppy_by_key[key]
            arca_amount = _safe_float(arca_rec.get("importe_total", 0))
            colppy_amt = _safe_float(colppy_rec.get("totalFactura", "0"))

            arca_summary = _arca_record_summary(arca_rec)
            colppy_summary = _colppy_record_summary(colppy_rec, cuit_map)

            # Percepciones comparison
            arca_otros = _safe_float(arca_rec.get("otros_tributos"))
            colppy_percepciones = colppy_summary["totalPercepciones"]
            percepciones_diff = round(arca_otros - colppy_percepciones, 2) if arca_otros else None

            # CUIT validation
            arca_cuit = _normalize_cuit(arca_rec.get("cuit_contraparte", ""))
            colppy_cuit = colppy_summary.get("cuit_proveedor", "")
            cuit_match = (arca_cuit == colppy_cuit) if arca_cuit and colppy_cuit else None

            pair_meta = {
                "arca": arca_summary,
                "colppy": colppy_summary,
                "percepciones_diff": percepciones_diff,
                "cuit_match": cuit_match,
            }

            if abs(arca_amount - colppy_amt) < 0.02:
                matched += 1
                matched_pairs.append(pair_meta)
            else:
                amount_mismatch += 1
                discrepancies.append({
                    "status": "amount_mismatch",
                    **pair_meta,
                    "diff_pesos": round(arca_amount - colppy_amt, 2),
                })
            continue

        # Not matched by compound key — try nro-only fallback below
        pass

    # ── Fallback: nro-only matching for CUIT resolution gaps ──
    # When a Colppy supplier lacks CUIT, compound keys won't align.
    # Collect unmatched items, group by bare nro, and match 1:1 pairs.
    arca_unmatched = {k: v for k, v in arca_by_key.items() if k not in matched_keys}
    colppy_unmatched = {k: v for k, v in colppy_by_key.items() if k not in matched_keys}

    arca_orphan_by_nro: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for k, v in arca_unmatched.items():
        arca_orphan_by_nro[_extract_nro_from_key(k)].append((k, v))

    colppy_orphan_by_nro: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for k, v in colppy_unmatched.items():
        colppy_orphan_by_nro[_extract_nro_from_key(k)].append((k, v))

    fallback_matched_arca: set[str] = set()
    fallback_matched_colppy: set[str] = set()

    for nro in set(arca_orphan_by_nro) & set(colppy_orphan_by_nro):
        arca_candidates = arca_orphan_by_nro[nro]
        colppy_candidates = colppy_orphan_by_nro[nro]
        # Only safe to match when exactly one from each side (unambiguous)
        if len(arca_candidates) == 1 and len(colppy_candidates) == 1:
            a_key, arca_rec = arca_candidates[0]
            c_key, colppy_rec = colppy_candidates[0]
            arca_amount = _safe_float(arca_rec.get("importe_total", 0))
            colppy_amt = _safe_float(colppy_rec.get("totalFactura", "0"))

            arca_summary = _arca_record_summary(arca_rec)
            colppy_summary = _colppy_record_summary(colppy_rec, cuit_map)

            arca_otros = _safe_float(arca_rec.get("otros_tributos"))
            colppy_percepciones = colppy_summary["totalPercepciones"]
            percepciones_diff = round(arca_otros - colppy_percepciones, 2) if arca_otros else None

            arca_cuit = _normalize_cuit(arca_rec.get("cuit_contraparte", ""))
            colppy_cuit = colppy_summary.get("cuit_proveedor", "")
            cuit_match = (arca_cuit == colppy_cuit) if arca_cuit and colppy_cuit else None

            pair_meta = {
                "arca": arca_summary,
                "colppy": colppy_summary,
                "percepciones_diff": percepciones_diff,
                "cuit_match": cuit_match,
            }

            if abs(arca_amount - colppy_amt) < 0.02:
                matched += 1
                matched_pairs.append(pair_meta)
            else:
                amount_mismatch += 1
                discrepancies.append({
                    "status": "amount_mismatch",
                    **pair_meta,
                    "diff_pesos": round(arca_amount - colppy_amt, 2),
                })

            fallback_matched_arca.add(a_key)
            fallback_matched_colppy.add(c_key)

    # Remaining unmatched → only_arca / only_colppy
    for key, rec in arca_unmatched.items():
        if key not in fallback_matched_arca:
            discrepancies.append({
                "status": "only_arca",
                "arca": _arca_record_summary(rec),
                "colppy": None,
            })

    for key, rec in colppy_unmatched.items():
        if key not in fallback_matched_colppy:
            discrepancies.append({
                "status": "only_colppy",
                "arca": None,
                "colppy": _colppy_record_summary(rec, cuit_map),
            })

    only_arca = sum(1 for d in discrepancies if d["status"] == "only_arca")
    only_colppy = sum(1 for d in discrepancies if d["status"] == "only_colppy")

    # --- Step 6: Retenciones overlay ---
    yield _sse({"type": "progress", "step": 6, "total": total_steps, "pct": 85,
                "message": "Vinculando retenciones..."})

    ret_index = _build_retenciones_index(cuit_representado, fecha_desde, fecha_hasta)
    retenciones_linked = 0

    if ret_index:
        # Annotate matched pairs with linked retenciones
        for pair in matched_pairs:
            supplier_cuit = (
                pair["arca"].get("cuit_contraparte")
                or pair["colppy"].get("cuit_proveedor")
                or ""
            )
            fecha = pair["arca"].get("fecha_emision") or pair["colppy"].get("fechaFactura") or ""
            linked = _get_linked_retenciones(ret_index, supplier_cuit, fecha)
            if linked:
                pair["retenciones"] = linked
                pair["retenciones_total"] = round(sum(r["importeRetenido"] for r in linked), 2)
                retenciones_linked += 1

        # Also annotate discrepancies
        for disc in discrepancies:
            supplier_cuit = ""
            fecha = ""
            if disc.get("arca"):
                supplier_cuit = disc["arca"].get("cuit_contraparte", "")
                fecha = disc["arca"].get("fecha_emision", "")
            elif disc.get("colppy"):
                supplier_cuit = disc["colppy"].get("cuit_proveedor", "")
                fecha = disc["colppy"].get("fechaFactura", "")
            linked = _get_linked_retenciones(ret_index, supplier_cuit, fecha)
            if linked:
                disc["retenciones"] = linked
                disc["retenciones_total"] = round(sum(r["importeRetenido"] for r in linked), 2)

    # Total retenciones in cache for this range
    all_retenciones = []
    for rets in ret_index.values():
        all_retenciones.extend(rets)
    total_retenciones_amount = round(sum(r["importeRetenido"] for r in all_retenciones), 2)

    # --- Done ---
    yield _sse({"type": "progress", "step": 6, "total": total_steps, "pct": 100,
                "message": f"Listo — {matched} matcheados, {len(discrepancies)} discrepancias"})

    # Count Colppy anuladas for data quality warnings
    colppy_anuladas = sum(
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
            "only_arca": only_arca,
            "only_colppy": only_colppy,
            "arca_no_number": len(arca_no_nro),
            "colppy_no_number": len(colppy_no_nro),
            "arca_duplicate_number": len(arca_dup),
            "colppy_duplicate_number": len(colppy_dup),
            "arca_importe_total": round(arca_total_pesos, 2),
            "colppy_importe_total": round(colppy_total_pesos, 2),
            "retenciones_cached": len(all_retenciones),
            "retenciones_linked": retenciones_linked,
            "retenciones_total": total_retenciones_amount,
            "colppy_anuladas": colppy_anuladas,
        },
        "arca_fetched_at": arca_fetched,
        "arca_auto_fetched": arca_auto_fetched,
        "proveedores_count": len(proveedores),
        "discrepancies": discrepancies,
        "matched_pairs": matched_pairs,
    }})
