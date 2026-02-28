#!/usr/bin/env python3
"""Colppy ↔ HubSpot Reconciliation (DB Only).

Reconciles Colppy first payments with HubSpot closed won for a given month.
**Colppy is master** — fechaPago and id_empresa from Colppy dictate; HubSpot should align.

Mismatch reasons:
- **close_date**: Colppy fechaPago ≠ HubSpot close_date (sales may have forced wrong month)
- **WRONG_STAGE**: Deal exists in HubSpot but stage is not closed-won (requires deals_any_stage populated)
- **id_empresa**: HubSpot has CRM id instead of Colppy id, or deal missing

Uses only local DBs: colppy_export.db and facturacion_hubspot.db (no API calls).
For WRONG_STAGE detection, run build with --refresh-deals-only --year YYYY --month M --fetch-wrong-stage first.

Usage:
  python tools/scripts/colppy/reconcile_colppy_hubspot_db_only.py --year 2026 --month 1
  python tools/scripts/colppy/reconcile_colppy_hubspot_db_only.py --year 2026 --month 1 --output tools/outputs/reconcile_202601_db.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "tools" / ".env")

DEFAULT_COLPPY_DB = REPO_ROOT / "tools/data/colppy_export.db"
DEFAULT_HUBSPOT_DB = REPO_ROOT / "tools/data/facturacion_hubspot.db"


def _validate_args(year: str, month: int) -> str | None:
    """Validate year and month. Returns error message or None if valid."""
    if not (1 <= month <= 12):
        return f"--month must be between 1 and 12, got {month}"
    if not year.isdigit() or len(year) != 4:
        return f"--year must be a 4-digit year, got {year!r}"
    return None


def run_reconciliation_data(
    year: str,
    month: int,
    colppy_db: Path,
    hubspot_db: Path,
) -> dict | None:
    """Run reconciliation and return JSON-serializable data for plugin snapshot. Returns None if DBs missing."""
    if not colppy_db.exists() or not hubspot_db.exists():
        return None
    from tools.scripts.colppy.reconcile_db_queries import (
        get_deal_any_stage,
        get_deal_for_id_empresa,
        get_hubspot_only_colppy_status,
        load_colppy_first_payments,
        load_hubspot_closed_won_from_db,
    )
    from tools.scripts.colppy.reconcile_helpers import dates_match, norm_date, plan_mismatch, sort_key_id_empresa
    from tools.scripts.colppy.reconcile_db_queries import get_empresa_activa_map
    from tools.scripts.colppy.reconcile_report_builder import build_report_json

    month_key = f"{year}-{month:02d}"
    colppy = load_colppy_first_payments(colppy_db, year, month)
    colppy_by_id = {str(r["idEmpresa"]): r for r in colppy}
    colppy_ids = set(colppy_by_id.keys())
    hubspot, _, _ = load_hubspot_closed_won_from_db(hubspot_db, year, month)
    hubspot_by_id = {str(r["id_empresa"]): r for r in hubspot}
    hubspot_ids = set(hubspot_by_id.keys())
    match_ids = colppy_ids & hubspot_ids
    colppy_only = colppy_ids - hubspot_ids
    hubspot_only = hubspot_ids - colppy_ids

    match_ok, match_ok_id_plan_blank, match_ok_id_plan_hubspot_has, match_ok_plan_mismatch = [], [], [], []
    match_fecha_primer_pago_blank = []
    match_close_date_mismatch = []
    for ie in match_ids:
        c, h = colppy_by_id[ie], hubspot_by_id[ie]
        if not dates_match(c.get("fechaPago", ""), h.get("close_date", "")):
            match_close_date_mismatch.append(ie)
            continue
        colppy_plan = str(c.get("idPlan") or "").strip()
        hubspot_plan = str(h.get("id_plan", "") or "").strip()
        if plan_mismatch(colppy_plan, hubspot_plan):
            match_ok_plan_mismatch.append(ie)
        elif colppy_plan and not hubspot_plan:
            match_ok_id_plan_blank.append(ie)
        elif not colppy_plan and hubspot_plan:
            match_ok_id_plan_hubspot_has.append(ie)
        else:
            match_ok.append(ie)
    for ie in match_ok + match_ok_id_plan_blank + match_ok_id_plan_hubspot_has + match_ok_plan_mismatch:
        c, h = colppy_by_id[ie], hubspot_by_id[ie]
        colppy_fecha = norm_date(c.get("fechaPago", ""))
        hub_fecha_pago = norm_date(h.get("fecha_primer_pago", ""))
        if colppy_fecha and not hub_fecha_pago:
            match_fecha_primer_pago_blank.append(ie)
    match_ok = [ie for ie in match_ok if ie not in match_fecha_primer_pago_blank]

    colppy_only_reasons = {}
    colppy_only_deal = {}
    for ie in colppy_only:
        deal = get_deal_for_id_empresa(hubspot_db, ie)
        if deal:
            colppy_only_reasons[ie] = "WRONG_CLOSE_DATE"
            colppy_only_deal[ie] = deal
        else:
            deal_any = get_deal_any_stage(hubspot_db, ie)
            if deal_any:
                colppy_only_reasons[ie] = "WRONG_STAGE"
                colppy_only_deal[ie] = deal_any
            else:
                colppy_only_reasons[ie] = "NO_HUBSPOT_DEAL"

    hubspot_only_status = get_hubspot_only_colppy_status(colppy_db, list(hubspot_only))
    all_ids = list(colppy_ids | hubspot_ids)
    activa_map = get_empresa_activa_map(colppy_db, all_ids)

    def _activa_val(ie: str) -> int:
        val, _ = activa_map.get(ie, (-1, "—"))
        return val if isinstance(val, int) else -1

    wrong_stage_case1 = {ie for ie in hubspot_ids if _activa_val(ie) != 0}
    wrong_stage_case2 = [
        ie for ie in colppy_only
        if _activa_val(ie) == 0 and colppy_only_reasons.get(ie) in ("WRONG_STAGE", "NO_HUBSPOT_DEAL")
    ]
    group3_ids = list(wrong_stage_case1 | set(wrong_stage_case2))
    group3_reasons = {}
    for ie in wrong_stage_case1:
        group3_reasons[ie] = "COLPPY_NOT_ACTIVE"
    for ie in wrong_stage_case2:
        group3_reasons[ie] = colppy_only_reasons.get(ie, "—")

    match_close_date_mismatch_filtered = [ie for ie in match_close_date_mismatch if ie not in wrong_stage_case1]
    hubspot_only_filtered = [ie for ie in hubspot_only if ie not in wrong_stage_case1]

    return build_report_json(
        month_key=month_key,
        colppy_by_id=colppy_by_id,
        hubspot_by_id=hubspot_by_id,
        match_ok=match_ok,
        match_ok_id_plan_blank=match_ok_id_plan_blank,
        match_ok_id_plan_hubspot_has=match_ok_id_plan_hubspot_has,
        match_ok_plan_mismatch=match_ok_plan_mismatch,
        match_close_date_mismatch=match_close_date_mismatch_filtered,
        colppy_only=colppy_only,
        colppy_only_reasons=colppy_only_reasons,
        colppy_only_deal=colppy_only_deal,
        hubspot_only=hubspot_only_filtered,
        hubspot_only_status=hubspot_only_status,
        colppy_db=colppy_db,
        group3_ids=group3_ids,
        group3_reasons=group3_reasons,
        group3_case1_ids=wrong_stage_case1,
    )


def run(
    year: str,
    month: int,
    colppy_db: Path,
    hubspot_db: Path,
    output_path: str | None = None,
    output_format: str = "markdown",
    post_slack_dm: bool = False,
    slack_user_id: str | None = None,
    db_path: str | None = None,
    no_log: bool = False,
) -> None:
    """Run DB-only reconciliation."""
    from tools.scripts.colppy.reconcile_db_queries import (
        get_deal_any_stage,
        get_deal_for_id_empresa,
        get_hubspot_only_colppy_status,
        load_colppy_first_payments,
        load_hubspot_closed_won_from_db,
    )
    from tools.scripts.colppy.reconcile_helpers import dates_match, norm_date, plan_mismatch, sort_key_id_empresa
    from tools.scripts.colppy.reconcile_report_builder import build_report, build_report_slack

    month_key = f"{year}-{month:02d}"
    print(f"Colppy ↔ HubSpot Reconciliation (DB Only) — {month_key}")
    print("=" * 70)

    if not colppy_db.exists():
        print(f"Error: Colppy DB not found: {colppy_db}")
        print("Run export_colppy_to_sqlite.py first.")
        return
    if not hubspot_db.exists():
        print(f"Error: HubSpot DB not found: {hubspot_db}")
        return

    try:
        print(f"Loading Colppy first payments from {colppy_db.name}...")
        colppy = load_colppy_first_payments(colppy_db, year, month)
    except Exception as e:
        print(f"Error loading Colppy data: {e}")
        raise

    colppy_by_id = {str(r["idEmpresa"]): r for r in colppy}
    colppy_ids = set(colppy_by_id.keys())
    print(f"  Colppy: {len(colppy):,} first payments ({len(colppy_ids):,} unique id_empresa)")

    try:
        print(f"Loading HubSpot closed won from {hubspot_db.name}...")
        hubspot, _, _ = load_hubspot_closed_won_from_db(hubspot_db, year, month)
    except Exception as e:
        print(f"Error loading HubSpot data: {e}")
        raise

    hubspot_by_id = {str(r["id_empresa"]): r for r in hubspot}
    hubspot_ids = set(hubspot_by_id.keys())
    print(f"  HubSpot: {len(hubspot):,} closed won deals ({len(hubspot_ids):,} unique id_empresa)")

    match_ids = colppy_ids & hubspot_ids
    colppy_only = colppy_ids - hubspot_ids
    hubspot_only = hubspot_ids - colppy_ids

    # fecha_primer_pago alignment (display only)
    fecha_primer_pago_match_count = 0
    fecha_primer_pago_diff_count = 0
    for ie in match_ids:
        c, h = colppy_by_id[ie], hubspot_by_id[ie]
        colppy_fecha = norm_date(c.get("fechaPago", ""))
        hub_fecha = norm_date(h.get("fecha_primer_pago", ""))
        if colppy_fecha and hub_fecha:
            if colppy_fecha == hub_fecha:
                fecha_primer_pago_match_count += 1
            else:
                fecha_primer_pago_diff_count += 1

    # Colppy is master: split MATCH by close_date alignment, then by id_plan alignment
    match_ok = []
    match_ok_id_plan_blank = []
    match_ok_id_plan_hubspot_has = []
    match_ok_plan_mismatch = []
    match_close_date_mismatch = []
    for ie in match_ids:
        c, h = colppy_by_id[ie], hubspot_by_id[ie]
        if not dates_match(c.get("fechaPago", ""), h.get("close_date", "")):
            match_close_date_mismatch.append(ie)
            continue
        colppy_plan = str(c.get("idPlan") or "").strip()
        hubspot_plan = str(h.get("id_plan", "") or "").strip()
        if plan_mismatch(colppy_plan, hubspot_plan):
            match_ok_plan_mismatch.append(ie)
        elif colppy_plan and not hubspot_plan:
            match_ok_id_plan_blank.append(ie)
        elif not colppy_plan and hubspot_plan:
            match_ok_id_plan_hubspot_has.append(ie)
        else:
            match_ok.append(ie)

    match_fecha_primer_pago_blank = []
    for ie in match_ok + match_ok_id_plan_blank + match_ok_id_plan_hubspot_has + match_ok_plan_mismatch:
        c, h = colppy_by_id[ie], hubspot_by_id[ie]
        colppy_fecha = norm_date(c.get("fechaPago", ""))
        hub_fecha_pago = norm_date(h.get("fecha_primer_pago", ""))
        if colppy_fecha and not hub_fecha_pago:
            match_fecha_primer_pago_blank.append(ie)
    match_ok = [ie for ie in match_ok if ie not in match_fecha_primer_pago_blank]

    # Infer reasons for Colppy only
    # NO_HUBSPOT_DEAL = in Colppy DB, no id_empresa in HubSpot (no closed-won deal for this id)
    # WRONG_STAGE = deal exists in HubSpot but not closed-won (e.g. closed churn)
    colppy_only_reasons = {}
    colppy_only_deal = {}
    for ie in colppy_only:
        deal = get_deal_for_id_empresa(hubspot_db, ie)
        if deal:
            colppy_only_reasons[ie] = "WRONG_CLOSE_DATE"
            colppy_only_deal[ie] = deal
        else:
            deal_any = get_deal_any_stage(hubspot_db, ie)
            if deal_any:
                colppy_only_reasons[ie] = "WRONG_STAGE"
                colppy_only_deal[ie] = deal_any
            else:
                colppy_only_reasons[ie] = "NO_HUBSPOT_DEAL"

    hubspot_only_status = get_hubspot_only_colppy_status(colppy_db, list(hubspot_only))

    # Wrong Stage: two cases based on activa
    # Case 1: activa != 0 (Colppy company inactive), HubSpot closed-won — COLPPY_NOT_ACTIVE
    # Case 2: activa == 0 (Colppy company active), HubSpot not closed-won — WRONG_STAGE, NO_HUBSPOT_DEAL
    from tools.scripts.colppy.reconcile_db_queries import get_empresa_activa_map

    all_ids = list(colppy_ids | hubspot_ids)
    activa_map = get_empresa_activa_map(colppy_db, all_ids)

    def _activa_val(ie: str) -> int:
        val, _ = activa_map.get(ie, (-1, "—"))
        return val if isinstance(val, int) else -1

    wrong_stage_case1 = {ie for ie in hubspot_ids if _activa_val(ie) != 0}
    wrong_stage_case2 = [
        ie for ie in colppy_only
        if _activa_val(ie) == 0
        and colppy_only_reasons.get(ie) in ("WRONG_STAGE", "NO_HUBSPOT_DEAL")
    ]
    group3_ids = list(wrong_stage_case1 | set(wrong_stage_case2))
    group3_reasons = {}
    for ie in wrong_stage_case1:
        group3_reasons[ie] = "COLPPY_NOT_ACTIVE"
    for ie in wrong_stage_case2:
        group3_reasons[ie] = colppy_only_reasons.get(ie, "—")

    # Exclude case1 from groups 1 and 4
    match_close_date_mismatch_filtered = [ie for ie in match_close_date_mismatch if ie not in wrong_stage_case1]
    hubspot_only_filtered = [ie for ie in hubspot_only if ie not in wrong_stage_case1]

    # Bucket splits for logging (progress tracking)
    hubspot_only_strict = {ie for ie in hubspot_only if hubspot_only_status.get(ie, {}).get("reason") == "NOT_IN_COLPPY"}
    hubspot_colppy_discrepancy = {
        ie for ie in hubspot_only
        if hubspot_only_status.get(ie, {}).get("reason") in ("IN_EMPRESA_NO_PAGO", "PRIMER_PAGO_OTHER_MONTH", "IN_EMPRESA_PAGO_NO_PRIMER")
    }
    colppy_wrong_close_date = [ie for ie in colppy_only if colppy_only_reasons.get(ie) == "WRONG_CLOSE_DATE"]
    colppy_wrong_stage = [ie for ie in colppy_only if colppy_only_reasons.get(ie) == "WRONG_STAGE"]
    colppy_no_deal = [ie for ie in colppy_only if colppy_only_reasons.get(ie) == "NO_HUBSPOT_DEAL"]
    hubspot_discrepancy_in_empresa_no_pago = [ie for ie in hubspot_colppy_discrepancy if hubspot_only_status.get(ie, {}).get("reason") == "IN_EMPRESA_NO_PAGO"]
    hubspot_discrepancy_primer_pago_other = [ie for ie in hubspot_colppy_discrepancy if hubspot_only_status.get(ie, {}).get("reason") == "PRIMER_PAGO_OTHER_MONTH"]
    hubspot_discrepancy_in_empresa_pago_no_primer = [ie for ie in hubspot_colppy_discrepancy if hubspot_only_status.get(ie, {}).get("reason") == "IN_EMPRESA_PAGO_NO_PRIMER"]

    if output_format == "slack":
        report = build_report_slack(
            month_key=month_key,
            colppy_by_id=colppy_by_id,
            hubspot_by_id=hubspot_by_id,
            match_ok=match_ok,
            match_ok_id_plan_blank=match_ok_id_plan_blank,
            match_ok_id_plan_hubspot_has=match_ok_id_plan_hubspot_has,
            match_ok_plan_mismatch=match_ok_plan_mismatch,
            match_fecha_primer_pago_blank=match_fecha_primer_pago_blank,
            match_close_date_mismatch=match_close_date_mismatch_filtered,
            colppy_only=colppy_only,
            colppy_only_reasons=colppy_only_reasons,
            colppy_only_deal=colppy_only_deal,
            hubspot_only=hubspot_only_filtered,
            hubspot_only_status=hubspot_only_status,
            fecha_primer_pago_match_count=fecha_primer_pago_match_count,
            fecha_primer_pago_diff_count=fecha_primer_pago_diff_count,
            colppy_db=colppy_db,
            group3_ids=group3_ids,
            group3_reasons=group3_reasons,
            group3_case1_ids=wrong_stage_case1,
        )
    else:
        report = build_report(
            month_key=month_key,
            colppy_by_id=colppy_by_id,
            hubspot_by_id=hubspot_by_id,
            match_ok=match_ok,
            match_ok_id_plan_blank=match_ok_id_plan_blank,
            match_ok_id_plan_hubspot_has=match_ok_id_plan_hubspot_has,
            match_ok_plan_mismatch=match_ok_plan_mismatch,
            match_fecha_primer_pago_blank=match_fecha_primer_pago_blank,
            match_close_date_mismatch=match_close_date_mismatch_filtered,
            colppy_only=colppy_only,
            colppy_only_reasons=colppy_only_reasons,
            colppy_only_deal=colppy_only_deal,
            hubspot_only=hubspot_only_filtered,
            hubspot_only_status=hubspot_only_status,
            fecha_primer_pago_match_count=fecha_primer_pago_match_count,
            fecha_primer_pago_diff_count=fecha_primer_pago_diff_count,
            colppy_db=colppy_db,
            group3_ids=group3_ids,
            group3_reasons=group3_reasons,
            group3_case1_ids=wrong_stage_case1,
        )

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"\nFull report written to: {out}")

    if post_slack_dm:
        import os
        from tools.utils.slack_post import post_slack_dm as _post_slack_dm

        uid = (slack_user_id or os.environ.get("SLACK_DM_USER_ID", "")).strip()
        if not uid:
            print("\nSlack DM skipped: SLACK_DM_USER_ID not set. Add to .env or use --slack-user-id.")
        else:
            # Use Slack format when posting to Slack
            dm_report = report if output_format == "slack" else build_report_slack(
                month_key=month_key,
                colppy_by_id=colppy_by_id,
                hubspot_by_id=hubspot_by_id,
                match_ok=match_ok,
                match_ok_id_plan_blank=match_ok_id_plan_blank,
                match_ok_id_plan_hubspot_has=match_ok_id_plan_hubspot_has,
                match_ok_plan_mismatch=match_ok_plan_mismatch,
                match_fecha_primer_pago_blank=match_fecha_primer_pago_blank,
                match_close_date_mismatch=match_close_date_mismatch_filtered,
                colppy_only=colppy_only,
                colppy_only_reasons=colppy_only_reasons,
                colppy_only_deal=colppy_only_deal,
                hubspot_only=hubspot_only_filtered,
                hubspot_only_status=hubspot_only_status,
                fecha_primer_pago_match_count=fecha_primer_pago_match_count,
                fecha_primer_pago_diff_count=fecha_primer_pago_diff_count,
                colppy_db=colppy_db,
                group3_ids=group3_ids,
                group3_reasons=group3_reasons,
                group3_case1_ids=wrong_stage_case1,
            )
            ok, msg = _post_slack_dm(uid, dm_report)
            if ok:
                print(f"\nSlack DM sent to {uid}.")
            else:
                print(f"\nSlack DM failed: {msg}")

    if not no_log and db_path:
        from tools.utils.reconciliation_logger import log_reconciliation

        log_reconciliation(
            db_path=db_path,
            script="reconcile_colppy_hubspot_db_only",
            reconciliation_type="colppy_first_payments_hubspot_closedwon",
            period=month_key,
            match_count=len(match_ids),
            source_a_total=len(colppy_ids),
            source_b_total=len(hubspot_ids),
            source_a_only_count=len(colppy_only),
            source_b_only_count=len(hubspot_only),
            match_ids=sorted(match_ids, key=sort_key_id_empresa),
            source_a_only_ids=sorted(colppy_only, key=sort_key_id_empresa),
            source_b_only_ids=sorted(hubspot_only, key=sort_key_id_empresa),
            source_metadata={"source": "db_only", "colppy_db": str(colppy_db), "hubspot_db": str(hubspot_db)},
            extra={
                "fecha_primer_pago_match_count": fecha_primer_pago_match_count,
                "fecha_primer_pago_diff_count": fecha_primer_pago_diff_count,
                # Match breakdown
                "match_ok_count": len(match_ok),
                "match_ok_ids": sorted(match_ok, key=sort_key_id_empresa),
                "match_ok_id_plan_blank_count": len(match_ok_id_plan_blank),
                "match_ok_id_plan_blank_ids": sorted(match_ok_id_plan_blank, key=sort_key_id_empresa),
                "match_ok_id_plan_hubspot_has_count": len(match_ok_id_plan_hubspot_has),
                "match_ok_id_plan_hubspot_has_ids": sorted(match_ok_id_plan_hubspot_has, key=sort_key_id_empresa),
                "match_ok_plan_mismatch_count": len(match_ok_plan_mismatch),
                "match_ok_plan_mismatch_ids": sorted(match_ok_plan_mismatch, key=sort_key_id_empresa),
                "match_fecha_primer_pago_blank_count": len(match_fecha_primer_pago_blank),
                "match_fecha_primer_pago_blank_ids": sorted(match_fecha_primer_pago_blank, key=sort_key_id_empresa),
                "match_close_date_mismatch_count": len(match_close_date_mismatch),
                "match_close_date_mismatch_ids": sorted(match_close_date_mismatch, key=sort_key_id_empresa),
                # Colppy unmatched breakdown
                "colppy_only_wrong_close_date_count": len(colppy_wrong_close_date),
                "colppy_only_wrong_close_date_ids": sorted(colppy_wrong_close_date, key=sort_key_id_empresa),
                "colppy_only_wrong_stage_count": len(colppy_wrong_stage),
                "colppy_only_wrong_stage_ids": sorted(colppy_wrong_stage, key=sort_key_id_empresa),
                "colppy_only_no_deal_count": len(colppy_no_deal),
                "colppy_only_no_deal_ids": sorted(colppy_no_deal, key=sort_key_id_empresa),
                # HubSpot breakdown (truly only vs discrepancy)
                "hubspot_only_strict_count": len(hubspot_only_strict),
                "hubspot_only_strict_ids": sorted(hubspot_only_strict, key=sort_key_id_empresa),
                "hubspot_colppy_discrepancy_count": len(hubspot_colppy_discrepancy),
                "hubspot_colppy_discrepancy_ids": sorted(hubspot_colppy_discrepancy, key=sort_key_id_empresa),
                "hubspot_discrepancy_in_empresa_no_pago_count": len(hubspot_discrepancy_in_empresa_no_pago),
                "hubspot_discrepancy_in_empresa_no_pago_ids": sorted(hubspot_discrepancy_in_empresa_no_pago, key=sort_key_id_empresa),
                "hubspot_discrepancy_primer_pago_other_month_count": len(hubspot_discrepancy_primer_pago_other),
                "hubspot_discrepancy_primer_pago_other_month_ids": sorted(hubspot_discrepancy_primer_pago_other, key=sort_key_id_empresa),
                "hubspot_discrepancy_in_empresa_pago_no_primer_count": len(hubspot_discrepancy_in_empresa_pago_no_primer),
                "hubspot_discrepancy_in_empresa_pago_no_primer_ids": sorted(hubspot_discrepancy_in_empresa_pago_no_primer, key=sort_key_id_empresa),
            },
        )
        print(f"\nReconciliation logged to {db_path}")

    print(report)


def main():
    parser = argparse.ArgumentParser(
        description="Colppy ↔ HubSpot reconciliation (DB only, no API)"
    )
    parser.add_argument("--year", type=str, required=True, help="Year (e.g. 2026)")
    parser.add_argument("--month", type=int, required=True, help="Month 1-12")
    parser.add_argument(
        "--colppy-db",
        type=str,
        default=str(DEFAULT_COLPPY_DB),
        help="Path to colppy_export.db",
    )
    parser.add_argument(
        "--hubspot-db",
        type=str,
        default=str(DEFAULT_HUBSPOT_DB),
        help="Path to facturacion_hubspot.db",
    )
    parser.add_argument("--output", "-o", type=str, help="Write full report to file")
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "slack"],
        default="markdown",
        help="Output format: markdown (default) or slack (Unicode tables for copy-paste to Slack)",
    )
    parser.add_argument(
        "--post-slack-dm",
        action="store_true",
        help="Post report to Slack DM (uses SLACK_DM_USER_ID from .env, or --slack-user-id)",
    )
    parser.add_argument(
        "--slack-user-id",
        type=str,
        help="Slack user ID for DM (overrides SLACK_DM_USER_ID). E.g. U01234567.",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(REPO_ROOT / "tools/data/facturacion_hubspot.db"),
        help="SQLite DB path for reconciliation logs",
    )
    parser.add_argument("--no-log", action="store_true", help="Skip logging to reconciliation_logs")
    args = parser.parse_args()

    err = _validate_args(args.year, args.month)
    if err:
        parser.error(err)

    output_path = args.output
    if args.format == "slack" and not output_path:
        output_path = str(REPO_ROOT / "tools/outputs" / f"reconcile_{args.year}{args.month:02d}_db.slack.txt")

    run(
        args.year,
        args.month,
        Path(args.colppy_db),
        Path(args.hubspot_db),
        output_path=output_path,
        output_format=args.format,
        post_slack_dm=args.post_slack_dm,
        slack_user_id=args.slack_user_id,
        db_path=None if args.no_log else args.db,
        no_log=args.no_log,
    )


if __name__ == "__main__":
    main()
