"""
Report generation for Colppy ↔ HubSpot reconciliation.

Report structure: 4 groups (see tools/docs/RECONCILE_REPORT_GROUPS.md)
1. Match but Mismatch in date = same month (fechaPago ≠ close_date)
2. Match but Mismatch in date = different month (fechaPago ≠ close_date)
3. Wrong Stage (Colppy has first payment; HubSpot deal wrong stage, wrong id_empresa, or missing)
4. Exist only in HubSpot
"""
from __future__ import annotations

from pathlib import Path

from .reconcile_db_queries import get_empresa_activa_map
from .reconcile_helpers import (
    fmt_amt,
    hubspot_deal_url,
    norm_date,
    sort_key_id_empresa,
)


def build_report(
    month_key: str,
    colppy_by_id: dict,
    hubspot_by_id: dict,
    match_ok: list,
    match_ok_id_plan_blank: list,
    match_ok_id_plan_hubspot_has: list,
    match_ok_plan_mismatch: list,
    match_fecha_primer_pago_blank: list,
    match_close_date_mismatch: list,
    colppy_only: set,
    colppy_only_reasons: dict,
    colppy_only_deal: dict,
    hubspot_only: set,
    hubspot_only_status: dict,
    fecha_primer_pago_match_count: int,
    fecha_primer_pago_diff_count: int,
    colppy_db: Path,
    group3_ids: list | None = None,
    group3_reasons: dict | None = None,
    group3_case1_ids: set | None = None,
) -> str:
    """Build full reconciliation report as markdown string (4-group structure)."""
    # Group 1: same month, wrong day
    group1_ids = list(match_close_date_mismatch)

    # Group 2: different month (WRONG_CLOSE_DATE)
    group2_ids = [ie for ie in colppy_only if colppy_only_reasons.get(ie) == "WRONG_CLOSE_DATE"]

    # Group 3: Wrong Stage — Case 1: activa≠0, HubSpot closed-won (COLPPY_NOT_ACTIVE)
    #          Case 2: activa=0, HubSpot not closed-won (WRONG_STAGE, NO_HUBSPOT_DEAL)
    if group3_ids is None or group3_reasons is None or group3_case1_ids is None:
        group3_ids = [
            ie for ie in colppy_only
            if colppy_only_reasons.get(ie) in ("WRONG_STAGE", "NO_HUBSPOT_DEAL")
        ]
        group3_reasons = colppy_only_reasons
        group3_case1_ids = set()

    # Group 4: exist only in HubSpot
    group4_ids = list(hubspot_only)

    match_full_count = (
        len(match_ok)
        + len(match_ok_id_plan_blank)
        + len(match_ok_id_plan_hubspot_has)
        + len(match_ok_plan_mismatch)
    )

    lines = []
    lines.append(f"# {month_key}: Colppy First Payments ↔ HubSpot Closed Won (DB Only)")
    lines.append("")
    lines.append("**Colppy is master.** Reconcile HubSpot to Colppy — update HubSpot deals to match Colppy first payments.")
    lines.append("")
    lines.append("**Report structure:** 4 groups. See `tools/docs/RECONCILE_REPORT_GROUPS.md` for definitions.")
    lines.append("")
    lines.append("**Sources:** colppy_export.db | facturacion_hubspot.db (deals + deals_any_stage)")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| MATCH (id_empresa + close_date + id_plan align) | {match_full_count} |")
    lines.append(f"| 1. Match but Mismatch in date = same month (fechaPago ≠ close_date) | {len(group1_ids)} |")
    lines.append(f"| 2. Match but Mismatch in date = different month (fechaPago ≠ close_date) | {len(group2_ids)} |")
    lines.append(f"| 3. Wrong Stage | {len(group3_ids)} |")
    lines.append(f"| 4. HubSpot closed-won this month, Colppy first payment in different month or absent | {len(group4_ids)} |")
    lines.append(f"| **Colppy total** | {len(colppy_by_id)} |")
    lines.append(f"| **HubSpot total** | {len(hubspot_by_id)} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Standard table header: activa beside HubSpot stage for easy comparison
    # nombre_del_plan_del_negocio = HubSpot product description entered by user
    header = (
        "| id_empresa | Colppy id_plan | HubSpot id_plan | HubSpot plan_name | HubSpot deal_type | nombre_del_plan_del_negocio | Colppy fechaPago | HubSpot close_date | HubSpot fecha_primer_pago | activa | HubSpot stage | "
        "Colppy medioPago | Colppy amount | HubSpot amount | HubSpot deal |"
    )
    sep = "|------------|---------------|----------------|-----------------|------------------|---------------------------|------------------|-------------------|---------------------------|--------|--------------|-----------------|---------------|----------------|--------------|"
    header_group3 = (
        "| id_empresa | Reason | HubSpot stage | Expected stage | Explanation | Colppy id_plan | HubSpot id_plan | HubSpot plan_name | HubSpot deal_type | nombre_del_plan_del_negocio | Colppy fechaPago | HubSpot close_date | HubSpot fecha_primer_pago | activa | Colppy medioPago | Colppy amount | HubSpot amount | HubSpot deal |"
    )
    sep_group3 = "|------------|--------|---------------|----------------|--------------|---------------|----------------|-----------------|------------------|---------------------------|------------------|-------------------|---------------------------|--------|-----------------|---------------|----------------|--------------|"

    # Group 1: same month, wrong day
    _append_group1(lines, group1_ids, colppy_by_id, hubspot_by_id, colppy_db, header, sep)

    # Group 2: different month
    _append_group2(lines, group2_ids, colppy_by_id, colppy_only_deal, colppy_db, header, sep)

    # Group 3: Wrong Stage (with Reason column)
    _append_group3(
        lines,
        group3_ids,
        colppy_by_id,
        hubspot_by_id,
        colppy_only_deal,
        group3_reasons,
        group3_case1_ids,
        colppy_db,
        header_group3,
        sep_group3,
    )

    # Group 4: exist only in HubSpot
    _append_group4(lines, group4_ids, hubspot_by_id, hubspot_only_status, colppy_db, header, sep)

    return "\n".join(lines)


def build_report_json(
    month_key: str,
    colppy_by_id: dict,
    hubspot_by_id: dict,
    match_ok: list,
    match_ok_id_plan_blank: list,
    match_ok_id_plan_hubspot_has: list,
    match_ok_plan_mismatch: list,
    match_close_date_mismatch: list,
    colppy_only: set,
    colppy_only_reasons: dict,
    colppy_only_deal: dict,
    hubspot_only: set,
    hubspot_only_status: dict,
    colppy_db: Path,
    group3_ids: list | None = None,
    group3_reasons: dict | None = None,
    group3_case1_ids: set | None = None,
) -> dict:
    """Build reconciliation report as JSON-serializable dict (for plugin snapshot)."""
    group1_ids = list(match_close_date_mismatch)
    group2_ids = [ie for ie in colppy_only if colppy_only_reasons.get(ie) == "WRONG_CLOSE_DATE"]
    if group3_ids is None or group3_reasons is None or group3_case1_ids is None:
        group3_ids = [ie for ie in colppy_only if colppy_only_reasons.get(ie) in ("WRONG_STAGE", "NO_HUBSPOT_DEAL")]
        group3_reasons = colppy_only_reasons
        group3_case1_ids = set()
    group4_ids = list(hubspot_only)
    match_full_count = len(match_ok) + len(match_ok_id_plan_blank) + len(match_ok_id_plan_hubspot_has) + len(match_ok_plan_mismatch)

    activa_map = get_empresa_activa_map(colppy_db, list(set(colppy_by_id.keys()) | set(hubspot_by_id.keys())))

    def _row(ie: str, c: dict | None, deal: dict | None, reason: str | None = None) -> dict:
        av, al = activa_map.get(ie, (-1, "—"))
        activa = f"{av} ({al})" if av >= 0 else al
        hub_url = hubspot_deal_url(deal["hubspot_id"]) if deal and deal.get("hubspot_id") else ""
        hub_name = (deal.get("deal_name") or "")[:35] if deal else ""
        return {
            "id_empresa": ie,
            "reason": reason,
            "colppy_id_plan": str(c.get("idPlan", "") or "") if c else "",
            "hubspot_id_plan": str(deal.get("id_plan", "") or "") if deal else "",
            "hubspot_plan_name": (deal.get("plan_name") or "") if deal else "",
            "hubspot_deal_type": (deal.get("deal_type") or "") if deal else "",
            "nombre_del_plan_del_negocio": (deal.get("nombre_del_plan_del_negocio") or "") if deal else "",
            "colppy_fecha_pago": norm_date(c.get("fechaPago", "")) if c else "",
            "hubspot_close_date": norm_date(deal.get("close_date", "")) if deal else "",
            "hubspot_fecha_primer_pago": norm_date(deal.get("fecha_primer_pago", "")) if deal else "",
            "activa": activa,
            "hubspot_stage": (deal.get("deal_stage") or "") if deal else "",
            "colppy_medio_pago": c.get("medioPago", "") if c else "",
            "colppy_amount": fmt_amt(c.get("importe")) if c else "",
            "hubspot_amount": fmt_amt(deal.get("amount")) if deal else "",
            "hubspot_deal_url": hub_url,
            "hubspot_deal_name": hub_name,
        }

    group1 = [_row(ie, colppy_by_id.get(ie), hubspot_by_id.get(ie)) for ie in sorted(group1_ids, key=sort_key_id_empresa)]
    group2 = [_row(ie, colppy_by_id.get(ie), colppy_only_deal.get(ie)) for ie in sorted(group2_ids, key=sort_key_id_empresa)]

    group3 = []
    for ie in sorted(group3_ids, key=sort_key_id_empresa):
        r = group3_reasons.get(ie, "—")
        in_case1 = ie in group3_case1_ids
        if in_case1:
            row = _row(ie, None, hubspot_by_id.get(ie), reason=r)
        else:
            row = _row(ie, colppy_by_id.get(ie), colppy_only_deal.get(ie), reason=r)
        exp_stage, explanation = _expected_stage_and_explanation(r, in_case1)
        row["expected_stage"] = exp_stage
        row["explanation"] = explanation
        group3.append(row)

    group4 = []
    for ie in sorted(group4_ids, key=sort_key_id_empresa):
        status = hubspot_only_status.get(ie, {})
        row = _row(ie, None, hubspot_by_id.get(ie))
        row["reason"] = status.get("reason", "")
        row["colppy_id_plan"] = str(status.get("id_plan") or "")
        row["colppy_fecha_pago"] = norm_date(status.get("colppy_fecha_pago") or "")
        row["colppy_medio_pago"] = status.get("colppy_medio_pago") or ""
        row["colppy_amount"] = fmt_amt(status.get("colppy_amount")) if status.get("colppy_amount") is not None else ""
        group4.append(row)

    return {
        "month_key": month_key,
        "summary": {
            "match_count": match_full_count,
            "group1_count": len(group1_ids),
            "group2_count": len(group2_ids),
            "group3_count": len(group3_ids),
            "group4_count": len(group4_ids),
            "colppy_total": len(colppy_by_id),
            "hubspot_total": len(hubspot_by_id),
        },
        "group1": group1,
        "group2": group2,
        "group3": group3,
        "group4": group4,
    }


def _expected_stage_and_explanation(reason: str, in_case1: bool) -> tuple[str, str]:
    """Return (expected_stage, explanation) for Wrong Stage group based on reason."""
    if reason == "COLPPY_NOT_ACTIVE" or in_case1:
        return (
            "closedlost",
            "Colppy company inactive; consider closedlost if churned.",
        )
    if reason == "WRONG_STAGE":
        return (
            "closedwon",
            "Colppy has first payment; deal should be closedwon.",
        )
    if reason == "NO_HUBSPOT_DEAL":
        return (
            "closedwon",
            "Create deal and set closedwon.",
        )
    return ("—", "—")


def _activa_cell(activa_map: dict, ie: str) -> str:
    """Format activa for table cell."""
    activa_val, activa_label = activa_map.get(ie, (-1, "—"))
    return f"{activa_val} ({activa_label})" if activa_val >= 0 else activa_label


def _hubspot_deal_link(deal: dict | None) -> str:
    """Build clickable HubSpot deal link."""
    if not deal or not deal.get("hubspot_id"):
        return ""
    name = (deal.get("deal_name") or "")[:35].replace("|", "-")
    return f"[{name}]({hubspot_deal_url(deal['hubspot_id'])})"


def _append_group1(
    lines: list,
    ids: list,
    colppy_by_id: dict,
    hubspot_by_id: dict,
    colppy_db: Path,
    header: str,
    sep: str,
) -> None:
    """Group 1: Match but Mismatch in date = same month."""
    lines.append("## 1. Match but Mismatch in date = same month (fechaPago ≠ close_date)")
    lines.append("")
    lines.append("Both in same month but exact day differs. **Action:** Set HubSpot close_date = Colppy fechaPago.")
    lines.append("")
    lines.append(header)
    lines.append(sep)
    if not ids:
        lines.append("| *(none)* | | | | | | | | | | | | | | |")
    else:
        activa_map = get_empresa_activa_map(colppy_db, ids)
        for ie in sorted(ids, key=sort_key_id_empresa):
            c, h = colppy_by_id[ie], hubspot_by_id[ie]
            activa = _activa_cell(activa_map, ie)
            link = _hubspot_deal_link(h)
            hub_stage = h.get("deal_stage", "") or ""
            plan_name = h.get("plan_name", "") or ""
            deal_type = h.get("deal_type", "") or ""
            nombre_plan = h.get("nombre_del_plan_del_negocio", "") or ""
            lines.append(
                f"| {ie} | {c.get('idPlan','')} | {h.get('id_plan','')} | {plan_name} | {deal_type} | {nombre_plan} | {norm_date(c.get('fechaPago',''))} | {norm_date(h.get('close_date',''))} | {norm_date(h.get('fecha_primer_pago',''))} | {activa} | {hub_stage} | "
                f"{c.get('medioPago','')} | {fmt_amt(c.get('importe'))} | {fmt_amt(h.get('amount'))} | {link} |"
            )
    lines.append("")
    lines.append("---")
    lines.append("")


def _append_group2(
    lines: list,
    ids: list,
    colppy_by_id: dict,
    colppy_only_deal: dict,
    colppy_db: Path,
    header: str,
    sep: str,
) -> None:
    """Group 2: Match but Mismatch in date = different month."""
    lines.append("## 2. Match but Mismatch in date = different month (fechaPago ≠ close_date)")
    lines.append("")
    lines.append("Colppy first payment this month; HubSpot deal exists but close_date in another month. **Action:** Set HubSpot close_date = Colppy fechaPago.")
    lines.append("")
    lines.append(header)
    lines.append(sep)
    if not ids:
        lines.append("| *(none)* | | | | | | | | | | | | | | |")
    else:
        activa_map = get_empresa_activa_map(colppy_db, ids)
        for ie in sorted(ids, key=sort_key_id_empresa):
            c = colppy_by_id[ie]
            deal = colppy_only_deal.get(ie)
            activa = _activa_cell(activa_map, ie)
            link = _hubspot_deal_link(deal)
            hub_id_plan = deal.get("id_plan", "") if deal else ""
            plan_name = (deal.get("plan_name", "") or "") if deal else ""
            deal_type = (deal.get("deal_type", "") or "") if deal else ""
            nombre_plan = (deal.get("nombre_del_plan_del_negocio", "") or "") if deal else ""
            hub_fecha = norm_date(deal.get("fecha_primer_pago", "")) if deal else ""
            hub_close = norm_date(deal.get("close_date", "")) if deal else ""
            hub_stage = (deal.get("deal_stage", "") or "") if deal else ""
            hub_amt = fmt_amt(deal.get("amount")) if deal else ""
            lines.append(
                f"| {ie} | {c.get('idPlan','')} | {hub_id_plan} | {plan_name} | {deal_type} | {nombre_plan} | {norm_date(c.get('fechaPago',''))} | {hub_close} | {hub_fecha} | {activa} | {hub_stage} | "
                f"{c.get('medioPago','')} | {fmt_amt(c.get('importe'))} | {hub_amt} | {link} |"
            )
    lines.append("")
    lines.append("---")
    lines.append("")


def _append_group3(
    lines: list,
    ids: list,
    colppy_by_id: dict,
    hubspot_by_id: dict,
    colppy_only_deal: dict,
    group3_reasons: dict,
    group3_case1_ids: set,
    colppy_db: Path,
    header: str,
    sep: str,
) -> None:
    """Group 3: Wrong Stage — Case 1: activa≠0, HubSpot closed-won (COLPPY_NOT_ACTIVE).
    Case 2: activa=0, HubSpot not closed-won (WRONG_STAGE, NO_HUBSPOT_DEAL)."""
    lines.append("## 3. Wrong Stage")
    lines.append("")
    lines.append(
        "**Case 1 (COLPPY_NOT_ACTIVE):** Colppy activa ≠ 0 (company inactive), HubSpot closed-won — mismatch. "
        "**Case 2:** Colppy activa = 0 (active), HubSpot deal wrong stage or missing. "
        "**Reasons:** COLPPY_NOT_ACTIVE, WRONG_STAGE, NO_HUBSPOT_DEAL (in Colppy, no id_empresa in HubSpot)."
    )
    lines.append("")
    lines.append(header)
    lines.append(sep)
    if not ids:
        lines.append("| *(none)* | | | | | | | | | | | | | | | | | |")
    else:
        activa_map = get_empresa_activa_map(colppy_db, ids)
        for ie in sorted(ids, key=sort_key_id_empresa):
            reason = group3_reasons.get(ie, "—")
            in_case1 = ie in group3_case1_ids
            exp_stage, explanation = _expected_stage_and_explanation(reason, in_case1)
            activa = _activa_cell(activa_map, ie)
            if in_case1:
                h = hubspot_by_id.get(ie, {})
                link = _hubspot_deal_link(h) if h.get("hubspot_id") else ""
                hub_id_plan = h.get("id_plan", "")
                plan_name = h.get("plan_name", "") or ""
                deal_type = h.get("deal_type", "") or ""
                nombre_plan = h.get("nombre_del_plan_del_negocio", "") or ""
                hub_fecha = norm_date(h.get("fecha_primer_pago", ""))
                hub_close = norm_date(h.get("close_date", ""))
                hub_stage = h.get("deal_stage", "") or ""
                hub_amt = fmt_amt(h.get("amount"))
                lines.append(
                    f"| {ie} | {reason} | {hub_stage} | {exp_stage} | {explanation} | | {hub_id_plan} | {plan_name} | {deal_type} | {nombre_plan} | | {hub_close} | {hub_fecha} | {activa} | "
                    f" | | {hub_amt} | {link} |"
                )
            else:
                c = colppy_by_id.get(ie, {})
                deal = colppy_only_deal.get(ie)
                link = _hubspot_deal_link(deal)
                hub_id_plan = deal.get("id_plan", "") if deal else ""
                plan_name = (deal.get("plan_name", "") or "") if deal else ""
                deal_type = (deal.get("deal_type", "") or "") if deal else ""
                nombre_plan = (deal.get("nombre_del_plan_del_negocio", "") or "") if deal else ""
                hub_fecha = norm_date(deal.get("fecha_primer_pago", "")) if deal else ""
                hub_close = norm_date(deal.get("close_date", "")) if deal else ""
                hub_stage = (deal.get("deal_stage", "") or "") if deal else ""
                hub_amt = fmt_amt(deal.get("amount")) if deal else ""
                lines.append(
                    f"| {ie} | {reason} | {hub_stage} | {exp_stage} | {explanation} | {c.get('idPlan','')} | {hub_id_plan} | {plan_name} | {deal_type} | {nombre_plan} | {norm_date(c.get('fechaPago',''))} | {hub_close} | {hub_fecha} | {activa} | "
                    f"{c.get('medioPago','')} | {fmt_amt(c.get('importe'))} | {hub_amt} | {link} |"
                )
    lines.append("")
    lines.append("---")
    lines.append("")


def _append_group4(
    lines: list,
    ids: list,
    hubspot_by_id: dict,
    hubspot_only_status: dict,
    colppy_db: Path,
    header: str,
    sep: str,
) -> None:
    """Group 4: Exist only in HubSpot."""
    lines.append("## 4. HubSpot closed-won this month, Colppy first payment in different month or absent")
    lines.append("")
    lines.append("HubSpot has closed-won this month; Colppy fechaPago is in a different month or Colppy has no first payment. **Reasons:** NOT_IN_COLPPY, IN_EMPRESA_NO_PAGO, PRIMER_PAGO_OTHER_MONTH, IN_EMPRESA_PAGO_NO_PRIMER.")
    lines.append("")
    lines.append(header)
    lines.append(sep)
    if not ids:
        lines.append("| *(none)* | | | | | | | | | | | | | | |")
    else:
        # For hubspot_only, Colppy cols from hubspot_only_status when primer pago in another month
        activa_map = get_empresa_activa_map(colppy_db, ids)
        for ie in sorted(ids, key=sort_key_id_empresa):
            h = hubspot_by_id[ie]
            status = hubspot_only_status.get(ie, {})
            activa = _activa_cell(activa_map, ie) if ie in activa_map else "—"
            link = ""
            if h.get("hubspot_id"):
                name = (h.get("deal_name") or "")[:35].replace("|", "-")
                link = f"[{name}]({hubspot_deal_url(h['hubspot_id'])})"
            hub_stage = h.get("deal_stage", "") or ""
            plan_name = h.get("plan_name", "") or ""
            deal_type = h.get("deal_type", "") or ""
            nombre_plan = h.get("nombre_del_plan_del_negocio", "") or ""
            colppy_id_plan = status.get("id_plan") or ""
            colppy_fecha = norm_date(status.get("colppy_fecha_pago") or "")
            colppy_medio = status.get("colppy_medio_pago") or ""
            colppy_amt = fmt_amt(status.get("colppy_amount")) if status.get("colppy_amount") is not None else ""
            lines.append(
                f"| {ie} | {colppy_id_plan} | {h.get('id_plan','')} | {plan_name} | {deal_type} | {nombre_plan} | {colppy_fecha} | {norm_date(h.get('close_date',''))} | {norm_date(h.get('fecha_primer_pago',''))} | {activa} | {hub_stage} | "
                f"{colppy_medio} | {colppy_amt} | {fmt_amt(h.get('amount'))} | {link} |"
            )
    lines.append("")


def build_report_slack(
    month_key: str,
    colppy_by_id: dict,
    hubspot_by_id: dict,
    match_ok: list,
    match_ok_id_plan_blank: list,
    match_ok_id_plan_hubspot_has: list,
    match_ok_plan_mismatch: list,
    match_fecha_primer_pago_blank: list,
    match_close_date_mismatch: list,
    colppy_only: set,
    colppy_only_reasons: dict,
    colppy_only_deal: dict,
    hubspot_only: set,
    hubspot_only_status: dict,
    fecha_primer_pago_match_count: int,
    fecha_primer_pago_diff_count: int,
    colppy_db: Path,
    group3_ids: list | None = None,
    group3_reasons: dict | None = None,
    group3_case1_ids: set | None = None,
) -> str:
    """Build Slack-friendly report with markdown-style tables and clickable HubSpot links.
    Uses <url|text> for links — do NOT wrap in code blocks or links won't be clickable."""
    group1_ids = list(match_close_date_mismatch)
    group2_ids = [ie for ie in colppy_only if colppy_only_reasons.get(ie) == "WRONG_CLOSE_DATE"]
    if group3_ids is not None and group3_reasons is not None and group3_case1_ids is not None:
        pass
    else:
        group3_ids = [ie for ie in colppy_only if colppy_only_reasons.get(ie) in ("WRONG_STAGE", "NO_HUBSPOT_DEAL")]
        group3_reasons = colppy_only_reasons
        group3_case1_ids = set()
    group4_ids = list(hubspot_only)
    match_full_count = len(match_ok) + len(match_ok_id_plan_blank) + len(match_ok_id_plan_hubspot_has) + len(match_ok_plan_mismatch)

    def _slack_link(deal: dict | None, fallback: str = "") -> str:
        """Build clickable Slack link <url|text>."""
        if not deal or not deal.get("hubspot_id"):
            return fallback
        url = hubspot_deal_url(deal["hubspot_id"])
        name = (deal.get("deal_name") or fallback)[:35].replace("|", "-").strip()
        # Remove trailing " ->" or " -" from truncated deal names
        if name.endswith(" ->"):
            name = name[:-3].strip()
        elif name.endswith(" -"):
            name = name[:-2].strip()
        return f"<{url}|{name}>"

    def _safe(s) -> str:
        """Escape pipes for markdown table cells."""
        return str(s or "").replace("|", "-")

    def _table_row(*cells: str) -> str:
        """Build a markdown table row with pipes."""
        return "| " + " | ".join(_safe(c) for c in cells) + " |"

    def _table_block(header: list[str], rows: list[list[str]]) -> list[str]:
        """Build markdown table inside code block for Slack (preserves pipe alignment)."""
        sep = "| " + " | ".join("---" for _ in header) + " |"
        out = [_table_row(*header), sep]
        for row in rows:
            out.append(_table_row(*row))
        return ["```"] + out + ["```"]

    lines = []
    lines.append(f"*{month_key} Colppy ↔ HubSpot Reconciliation*")
    lines.append("")
    lines.append("*Summary*")
    lines.extend(_table_block(
        ["Category", "Count"],
        [
            ["MATCH (align)", str(match_full_count)],
            ["1. Same month (fechaPago ≠ close_date)", str(len(group1_ids))],
            ["2. Different month", str(len(group2_ids))],
            ["3. Wrong Stage", str(len(group3_ids))],
            ["4. HubSpot only", str(len(group4_ids))],
            ["Colppy total", str(len(colppy_by_id))],
            ["HubSpot total", str(len(hubspot_by_id))],
        ],
    ))
    lines.append("")

    # Group 1: same month
    lines.append("*1. Same month — Set HubSpot close_date = Colppy fechaPago*")
    lines.append("")
    lines.append("Both in same month but exact day differs. *Action:* Set HubSpot close_date = Colppy fechaPago.")
    lines.append("")
    if group1_ids:
        rows = []
        links = []
        for ie in sorted(group1_ids, key=sort_key_id_empresa):
            c, h = colppy_by_id[ie], hubspot_by_id[ie]
            rows.append([ie, str(c.get("idPlan", "") or ""), str(h.get("id_plan", "") or ""), norm_date(c.get("fechaPago", "")), norm_date(h.get("close_date", "")), ie])
            links.append(_slack_link(h, ie))
        lines.extend(_table_block(["id_empresa", "Colppy id_plan", "HubSpot id_plan", "Colppy fechaPago", "HubSpot close_date", "Deal"], rows))
        lines.append("")
        lines.append("Deals: " + " · ".join(links))
    else:
        lines.append("_(none)_")
    lines.append("")

    # Group 2: different month
    lines.append("*2. Different month — Set HubSpot close_date = Colppy fechaPago*")
    lines.append("")
    lines.append("Colppy first payment this month; HubSpot deal exists but close_date in another month. *Action:* Set HubSpot close_date = Colppy fechaPago.")
    lines.append("")
    if group2_ids:
        rows = []
        links = []
        for ie in sorted(group2_ids, key=sort_key_id_empresa):
            c = colppy_by_id[ie]
            deal = colppy_only_deal.get(ie)
            hub_plan = str(deal.get("id_plan", "") or "") if deal else ""
            hub_close = norm_date(deal.get("close_date", "")) if deal else ""
            rows.append([ie, str(c.get("idPlan", "") or ""), hub_plan, norm_date(c.get("fechaPago", "")), hub_close, ie])
            links.append(_slack_link(deal, ie))
        lines.extend(_table_block(["id_empresa", "Colppy id_plan", "HubSpot id_plan", "Colppy fechaPago", "HubSpot close_date", "Deal"], rows))
        lines.append("")
        lines.append("Deals: " + " · ".join(links))
    else:
        lines.append("_(none)_")
    lines.append("")

    # Group 3: wrong stage
    lines.append("*3. Wrong Stage*")
    lines.append("")
    lines.append("Colppy has first payment; deal should be closedwon. *Action:* Update HubSpot stage or create deal.")
    lines.append("")
    if group3_ids:
        rows = []
        links = []
        for ie in sorted(group3_ids, key=sort_key_id_empresa):
            r = group3_reasons.get(ie, "—")
            in_case1 = ie in group3_case1_ids
            exp, _ = _expected_stage_and_explanation(r, in_case1)
            deal = hubspot_by_id.get(ie) or colppy_only_deal.get(ie)
            hub_stage = (deal.get("deal_stage") or "") if deal else ""
            rows.append([ie, r, hub_stage, exp, ie])
            links.append(_slack_link(deal, ie))
        lines.extend(_table_block(["id_empresa", "Reason", "H_stage", "Expected", "Deal"], rows))
        lines.append("")
        lines.append("Deals: " + " · ".join(links))
    else:
        lines.append("_(none)_")
    lines.append("")

    # Group 4: HubSpot only
    lines.append("*4. HubSpot only — Review*")
    lines.append("")
    lines.append("HubSpot closed-won this month; Colppy first payment in different month or absent. *Action:* Review.")
    lines.append("")
    if group4_ids:
        rows = []
        links = []
        for ie in sorted(group4_ids, key=sort_key_id_empresa):
            h = hubspot_by_id[ie]
            status = hubspot_only_status.get(ie, {})
            c_plan = str(status.get("id_plan") or "")
            c_fecha = norm_date(status.get("colppy_fecha_pago") or "")
            rows.append([ie, c_plan, str(h.get("id_plan", "") or ""), c_fecha, norm_date(h.get("close_date", "")), ie])
            links.append(_slack_link(h, ie))
        lines.extend(_table_block(["id_empresa", "Colppy id_plan", "HubSpot id_plan", "Colppy fechaPago", "HubSpot close_date", "Deal"], rows))
        lines.append("")
        lines.append("Deals: " + " · ".join(links))
    else:
        lines.append("_(none)_")

    return "\n".join(lines)
