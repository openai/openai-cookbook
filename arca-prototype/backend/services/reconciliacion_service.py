"""
Reconciliación de retenciones/percepciones contra comprobantes recibidos.

Both retenciones and comprobantes come from SQLite cache (passed in by the router).
Pure logic — no DB access, no Playwright.
"""
from collections import defaultdict
from typing import Any


def reconcile_retenciones(
    retenciones: list[dict[str, Any]],
    comprobantes: list[dict[str, Any]],
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> dict[str, Any]:
    """
    Main reconciliation: cross-reference retenciones against comprobantes recibidos.

    1. Group retenciones by (agent_cuit, YYYY-MM)
    2. Index comprobantes by (cuit_contraparte, YYYY-MM)
    3. For each group: find matching comprobantes, assign match_status
    4. Return structured result with summary + coverage info
    """
    if not retenciones:
        return {
            "success": True,
            "periodos": [],
            "summary": _empty_summary(),
            "comprobantes_data_coverage": _compute_coverage(comprobantes),
            "message": "No hay retenciones en caché para este rango. Descargue primero desde Mis Retenciones.",
        }

    # Step 1: group retenciones by (agent_cuit, YYYY-MM)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in retenciones:
        agent_cuit = str(r.get("cuitAgenteRetencion", ""))
        fecha = r.get("fechaRetencion", "")[:10]  # "2025-01-30"
        periodo = fecha[:7]  # "2025-01"
        groups[(agent_cuit, periodo)].append(r)

    # Step 2: index comprobantes by (cuit_contraparte, YYYY-MM)
    comp_index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    comp_months: set[str] = set()
    for c in comprobantes:
        cc = str(c.get("cuit_contraparte", ""))
        fe = c.get("fecha_emision", "")[:7]  # "2025-01"
        comp_index[(cc, fe)].append(c)
        comp_months.add(fe)

    # Step 3: build periodos
    periodos_map: dict[str, dict] = {}
    total_positivo = 0.0
    total_nc = 0.0
    grupos_matched = 0
    grupos_orphan = 0
    grupos_no_data = 0

    for (agent_cuit, periodo), rets in sorted(groups.items()):
        if periodo not in periodos_map:
            periodos_map[periodo] = {
                "periodo": periodo,
                "agentes": [],
                "total_retenido_mes": 0.0,
            }

        # Calculate subtotals for this agent in this month
        positivos = sum(r["importeRetenido"] for r in rets if r.get("importeRetenido", 0) > 0)
        negativos = sum(r["importeRetenido"] for r in rets if r.get("importeRetenido", 0) < 0)
        neto = positivos + negativos

        total_positivo += positivos
        total_nc += negativos

        # Determine match status
        matching_comps = comp_index.get((agent_cuit, periodo), [])
        if matching_comps:
            match_status = "matched"
            grupos_matched += 1
        elif comp_months and periodo in comp_months:
            # We have comprobantes for this month, but not from this agent
            match_status = "orphan"
            grupos_orphan += 1
        else:
            match_status = "no_data"
            grupos_no_data += 1

        # Agent name: use denominacion from matching comprobantes, or format CUIT
        nombre_agente = f"AGENTE {agent_cuit}"
        for comp in matching_comps:
            if comp.get("denominacion_contraparte"):
                nombre_agente = comp["denominacion_contraparte"]
                break

        agent_entry = {
            "cuit_agente": agent_cuit,
            "nombre_agente": nombre_agente,
            "retenciones": [
                {
                    "numeroCertificado": r.get("numeroCertificado", ""),
                    "fechaRetencion": r.get("fechaRetencion", ""),
                    "importeRetenido": r.get("importeRetenido", 0),
                    "descripcionOperacion": r.get("descripcionOperacion", ""),
                    "codigoRegimen": r.get("codigoRegimen", ""),
                    "impuestoRetenido": r.get("impuestoRetenido", ""),
                    "numeroComprobante": r.get("numeroComprobante", ""),
                    "fechaComprobante": r.get("fechaComprobante", ""),
                    "descripcionComprobante": r.get("descripcionComprobante", ""),
                }
                for r in rets
            ],
            "total_positivo": round(positivos, 2),
            "total_notas_credito": round(negativos, 2),
            "total_retenido": round(neto, 2),
            "match_status": match_status,
            "comprobantes": [
                {
                    "fecha_emision": c.get("fecha_emision", ""),
                    "tipo_comprobante": c.get("tipo_comprobante", ""),
                    "numero": c.get("numero", ""),
                    "importe_total": c.get("importe_total", 0),
                    "denominacion_contraparte": c.get("denominacion_contraparte", ""),
                }
                for c in matching_comps
            ],
        }

        periodos_map[periodo]["agentes"].append(agent_entry)
        periodos_map[periodo]["total_retenido_mes"] = round(
            periodos_map[periodo]["total_retenido_mes"] + neto, 2
        )

    # Sort periodos chronologically
    periodos = [periodos_map[k] for k in sorted(periodos_map.keys())]

    return {
        "success": True,
        "periodos": periodos,
        "summary": {
            "total_retenciones": len(retenciones),
            "total_positivo": round(total_positivo, 2),
            "total_notas_credito": round(total_nc, 2),
            "total_neto_para_ddjj": round(total_positivo + total_nc, 2),
            "grupos_matched": grupos_matched,
            "grupos_orphan": grupos_orphan,
            "grupos_no_data": grupos_no_data,
        },
        "comprobantes_data_coverage": _compute_coverage(comprobantes),
    }


def _empty_summary() -> dict:
    return {
        "total_retenciones": 0,
        "total_positivo": 0,
        "total_notas_credito": 0,
        "total_neto_para_ddjj": 0,
        "grupos_matched": 0,
        "grupos_orphan": 0,
        "grupos_no_data": 0,
    }


def _compute_coverage(comprobantes: list[dict]) -> dict[str, Any]:
    """Determine what period the comprobantes data covers."""
    if not comprobantes:
        return {"status": "none", "min": None, "max": None}
    months = set()
    for c in comprobantes:
        fe = c.get("fecha_emision", "")[:7]
        if fe:
            months.add(fe)
    if not months:
        return {"status": "none", "min": None, "max": None}
    return {
        "status": "partial",
        "min": min(months),
        "max": max(months),
    }
