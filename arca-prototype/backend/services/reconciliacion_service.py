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
    colppy_percepciones: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """
    Main reconciliation: cross-reference retenciones against comprobantes recibidos.

    1. Group retenciones by (agent_cuit, YYYY-MM)
    2. Index comprobantes by (cuit_contraparte, YYYY-MM)
    3. For each group: find matching comprobantes, assign match_status
    4. If colppy_percepciones provided, add Colppy comparison per agent
    5. Return structured result with summary + coverage info

    colppy_percepciones: optional dict keyed by normalized CUIT, each value
    is a list of Colppy invoice dicts with percepciones fields.
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
                    "fechaRetencion": r.get("fechaRetencion", "") or "",
                    "importeRetenido": r.get("importeRetenido", 0),
                    "descripcionOperacion": r.get("descripcionOperacion", ""),
                    "codigoRegimen": r.get("codigoRegimen", ""),
                    "impuestoRetenido": r.get("impuestoRetenido", ""),
                    "numeroComprobante": r.get("numeroComprobante", ""),
                    "fechaComprobante": r.get("fechaComprobante", "") or "",
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
                    "fecha_emision": c.get("fecha_emision", "") or "",
                    "tipo_comprobante": c.get("tipo_comprobante", ""),
                    "numero": c.get("numero", ""),
                    "importe_total": c.get("importe_total", 0),
                    "denominacion_contraparte": c.get("denominacion_contraparte", ""),
                }
                for c in matching_comps
            ],
        }

        # Colppy percepciones comparison (when data provided)
        if colppy_percepciones is not None:
            colppy_invoices = colppy_percepciones.get(agent_cuit, [])
            agent_entry["colppy_percepciones"] = [
                {
                    "nroFactura": inv.get("nroFactura", "") or "",
                    "fechaFactura": inv.get("fechaFactura", "") or "",
                    "RazonSocial": inv.get("RazonSocial", ""),
                    "totalFactura": inv.get("totalFactura", 0),
                    "percepcionIVA": inv.get("percepcionIVA", 0),
                    "percepcionIIBB": inv.get("percepcionIIBB", 0),
                    "totalPercepciones": inv.get("totalPercepciones", 0),
                }
                for inv in colppy_invoices
            ]
            colppy_total = round(sum(inv.get("totalPercepciones", 0) for inv in colppy_invoices), 2)
            agent_entry["colppy_percepciones_total"] = colppy_total
            agent_entry["percepciones_diff"] = round(neto - colppy_total, 2)
            # Use Colppy name if we didn't get one from comprobantes
            if nombre_agente.startswith("AGENTE ") and colppy_invoices:
                first_name = colppy_invoices[0].get("RazonSocial", "")
                if first_name:
                    agent_entry["nombre_agente"] = first_name

        periodos_map[periodo]["agentes"].append(agent_entry)
        periodos_map[periodo]["total_retenido_mes"] = round(
            periodos_map[periodo]["total_retenido_mes"] + neto, 2
        )

    # Sort periodos chronologically
    periodos = [periodos_map[k] for k in sorted(periodos_map.keys())]

    summary = {
        "total_retenciones": len(retenciones),
        "total_positivo": round(total_positivo, 2),
        "total_notas_credito": round(total_nc, 2),
        "total_neto_para_ddjj": round(total_positivo + total_nc, 2),
        "grupos_matched": grupos_matched,
        "grupos_orphan": grupos_orphan,
        "grupos_no_data": grupos_no_data,
    }

    result = {
        "success": True,
        "periodos": periodos,
        "summary": summary,
        "comprobantes_data_coverage": _compute_coverage(comprobantes),
    }

    # Colppy percepciones comparison summary
    if colppy_percepciones is not None:
        mirequa_cuits = {agent_cuit for (agent_cuit, _) in groups.keys()}
        colppy_total = round(
            sum(
                inv.get("totalPercepciones", 0)
                for invs in colppy_percepciones.values()
                for inv in invs
            ), 2,
        )
        mirequa_total = round(total_positivo + total_nc, 2)

        # Agents only in Colppy (have percepciones but no Mirequa certificates)
        only_colppy_agents = []
        for cuit, invs in sorted(colppy_percepciones.items()):
            if cuit not in mirequa_cuits and invs:
                agent_total = round(sum(inv.get("totalPercepciones", 0) for inv in invs), 2)
                only_colppy_agents.append({
                    "cuit_agente": cuit,
                    "nombre_agente": invs[0].get("RazonSocial", f"AGENTE {cuit}"),
                    "colppy_percepciones": [
                        {
                            "nroFactura": inv.get("nroFactura", "") or "",
                            "fechaFactura": inv.get("fechaFactura", "") or "",
                            "totalFactura": inv.get("totalFactura", 0),
                            "percepcionIVA": inv.get("percepcionIVA", 0),
                            "percepcionIIBB": inv.get("percepcionIIBB", 0),
                            "totalPercepciones": inv.get("totalPercepciones", 0),
                        }
                        for inv in invs
                    ],
                    "colppy_percepciones_total": agent_total,
                })

        summary["colppy_percepciones_total"] = colppy_total
        summary["mirequa_percepciones_total"] = mirequa_total
        summary["percepciones_diff"] = round(mirequa_total - colppy_total, 2)
        result["only_colppy_agents"] = only_colppy_agents

    return result


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
