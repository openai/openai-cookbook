#!/usr/bin/env python3
"""
HubSpot Deals ↔ Colppy DB CUIT Reconciliation
==============================================
Reconciles HubSpot deal primary company CUIT with Colppy DB CUIT (who we invoice).

**Alternative to facturacion.csv:** Uses Colppy DB as source of truth for billing CUIT,
instead of the billing system facturacion.csv. This answers: "Do HubSpot deals have
the right primary company (CUIT) for who we actually bill in Colppy?"

Logic:
- For each deal: PRIMARY company (association type 5) CUIT must match Colppy DB CUIT.
- Colppy CUIT from: facturacion.CUIT (primary), empresa.CUIT (fallback) — same as colppy_cuit_snapshot.

Uses: deals, deal_associations (type 5), companies, colppy_export.db (or colppy_cuit_snapshot.json).
Run populate_deal_associations.py first to ensure deal_associations is current.

Usage:
  python tools/scripts/colppy/reconcile_cuit_hubspot_colppy_db.py --year 2026 --month 2
  python tools/scripts/colppy/reconcile_cuit_hubspot_colppy_db.py --year 2026 --month 2 --output tools/outputs/cuit_reconcile_colppy_db_202602.md
  python tools/scripts/colppy/reconcile_cuit_hubspot_colppy_db.py  # all closed-won deals
"""
import argparse
import calendar
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

from tools.scripts.hubspot.hubspot_build_fetchers import format_cuit_display, normalize_cuit
from tools.scripts.colppy.reconcile_helpers import hubspot_deal_url, sort_key_id_empresa

load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "tools" / ".env")

DEFAULT_HUBSPOT_DB = REPO_ROOT / "tools/data/facturacion_hubspot.db"
DEFAULT_COLPPY_DB = REPO_ROOT / "tools/data/colppy_export.db"
DEFAULT_CUIT_SNAPSHOT = REPO_ROOT / "plugins/colppy-ceo-assistant/docs/colppy_cuit_snapshot.json"
PRIMARY_ASSOCIATION_TYPE = 5


def _normalize_cuit(cuit: str | None) -> str:
    """Normalize CUIT to 11 digits for comparison. Returns empty string if invalid."""
    n = normalize_cuit(cuit or "")
    return n or ""


def _format_cuit(cuit: str | None) -> str:
    """Format CUIT as 30-12345678-9 for display."""
    n = _normalize_cuit(cuit)
    return format_cuit_display(n) if n else (cuit or "")


def load_colppy_cuit_from_db(db_path: Path) -> dict[str, dict]:
    """Load id_empresa → {cuit, cuit_display, source, razon_social} from colppy_export.db."""
    from tools.scripts.colppy.export_colppy_cuit_snapshot import query_cuit_by_id_empresa

    rows = query_cuit_by_id_empresa(db_path)
    return {r["id_empresa"]: {k: v for k, v in r.items() if k != "id_empresa"} for r in rows}


def load_colppy_cuit_from_snapshot(snapshot_path: Path) -> dict[str, dict]:
    """Load id_empresa → CUIT from colppy_cuit_snapshot.json."""
    if not snapshot_path.exists():
        return {}
    try:
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {snapshot_path}: {e}")
        return {}
    return data.get("cuit_by_id_empresa", {})


def run(
    hubspot_db_path: Path,
    colppy_db_path: Path | None = None,
    cuit_snapshot_path: Path | None = None,
    year: str | None = None,
    month: int | None = None,
    output_path: str | None = None,
) -> bool:
    """
    Reconcile HubSpot deal primary company CUIT with Colppy DB CUIT.
    Uses Colppy DB (or colppy_cuit_snapshot.json) as source — alternative to facturacion.csv.
    Returns True on success, False on error.
    """
    if not hubspot_db_path.exists():
        print(f"Error: HubSpot DB not found: {hubspot_db_path}")
        return False

    # Load Colppy CUIT: prefer colppy_export.db, fallback to snapshot JSON
    colppy_cuit: dict[str, dict] = {}
    if colppy_db_path and colppy_db_path.exists():
        colppy_cuit = load_colppy_cuit_from_db(colppy_db_path)
    elif cuit_snapshot_path and cuit_snapshot_path.exists():
        colppy_cuit = load_colppy_cuit_from_snapshot(cuit_snapshot_path)
    else:
        print("Error: No Colppy CUIT source. Provide colppy_export.db or colppy_cuit_snapshot.json")
        return False

    month_key = ""
    if year and month:
        month_key = f"{year}-{month:02d}"
        start = f"{year}-{month:02d}-01"
        last_day = calendar.monthrange(int(year), month)[1]
        end = f"{year}-{month:02d}-{last_day:02d}"
        date_filter = "AND d.close_date >= ? AND d.close_date <= ?"
        date_params = (start, end)
    else:
        date_filter = ""
        date_params = ()

    with sqlite3.connect(str(hubspot_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        query = f"""
            SELECT
                d.id_empresa,
                d.hubspot_id,
                d.deal_name,
                d.close_date,
                da.company_hubspot_id AS primary_company_hs_id,
                c.cuit AS hubspot_primary_cuit
            FROM deals d
            LEFT JOIN deal_associations da ON da.deal_hubspot_id = d.hubspot_id AND da.association_type_id = 5
            LEFT JOIN companies c ON c.hubspot_id = da.company_hubspot_id
            WHERE d.deal_stage IN ('closedwon', '34692158')
            {date_filter}
            ORDER BY d.id_empresa
        """
        cur = conn.execute(query, date_params)
        rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        print(f"No closed-won deals found{f' for {month_key}' if month_key else ''}.")
        return True

    match = []
    mismatch = []
    no_primary = []
    no_colppy_cuit = []
    no_hubspot_cuit = []

    for r in rows:
        ie = str(r.get("id_empresa") or "").strip()
        colppy_row = colppy_cuit.get(ie, {})
        colppy_cuit_val = _normalize_cuit(colppy_row.get("cuit") or colppy_row.get("cuit_display", ""))
        hs_cuit = _normalize_cuit(r.get("hubspot_primary_cuit"))

        if not r.get("primary_company_hs_id"):
            no_primary.append({**r, "colppy_cuit": colppy_row.get("cuit_display", ""), "colppy_razon": colppy_row.get("razon_social", "")})
        elif not colppy_cuit_val:
            no_colppy_cuit.append(r)
        elif not hs_cuit:
            no_hubspot_cuit.append({**r, "colppy_cuit": colppy_row.get("cuit_display", ""), "colppy_razon": colppy_row.get("razon_social", "")})
        elif hs_cuit == colppy_cuit_val:
            match.append({**r, "colppy_cuit": colppy_row.get("cuit_display", ""), "colppy_razon": colppy_row.get("razon_social", "")})
        else:
            mismatch.append({**r, "colppy_cuit": colppy_row.get("cuit_display", ""), "colppy_razon": colppy_row.get("razon_social", "")})

    # Report
    lines = []
    title = "HubSpot Deals ↔ Colppy DB CUIT Reconciliation"
    if month_key:
        title += f" — {month_key}"
    lines.append(f"# {title}")
    lines.append("")
    lines.append("**Source:** Colppy DB (facturacion.CUIT / empresa.CUIT) — alternative to facturacion.csv from billing system.")
    lines.append("")
    lines.append("**Logic:** For each deal, the PRIMARY company (association type 5) CUIT must match Colppy DB CUIT (who we invoice).")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| MATCH (HubSpot primary CUIT = Colppy DB CUIT) | {len(match)} |")
    lines.append(f"| MISMATCH (CUIT differs) | {len(mismatch)} |")
    lines.append(f"| NO_PRIMARY (no type 5 association) | {len(no_primary)} |")
    lines.append(f"| NO_COLPPY_CUIT (id_empresa not in Colppy) | {len(no_colppy_cuit)} |")
    lines.append(f"| NO_HUBSPOT_CUIT (primary company has no CUIT in companies table) | {len(no_hubspot_cuit)} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    def _sort_key(r):
        return sort_key_id_empresa(r.get("id_empresa"))

    if mismatch:
        lines.append("## MISMATCH — HubSpot primary CUIT ≠ Colppy DB CUIT")
        lines.append("")
        lines.append("| id_empresa | deal_name | HubSpot primary CUIT | Colppy DB CUIT | Colppy razon_social |")
        lines.append("|------------|-----------|----------------------|----------------|---------------------|")
        for r in sorted(mismatch, key=_sort_key):
            name = (r.get("deal_name") or "")[:35]
            hs = _format_cuit(r.get("hubspot_primary_cuit"))
            cp = r.get("colppy_cuit", "")
            rs = (r.get("colppy_razon") or "")[:30]
            lines.append(f"| {r['id_empresa']} | {name} | {hs} | {cp} | {rs} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    if no_primary:
        lines.append("## NO_PRIMARY — Deal has no PRIMARY (type 5) company association")
        lines.append("")
        lines.append("| id_empresa | deal_name | close_date | Colppy DB CUIT | Colppy razon_social | HubSpot deal |")
        lines.append("|------------|-----------|------------|----------------|---------------------|--------------|")
        for r in sorted(no_primary, key=_sort_key):
            name = (r.get("deal_name") or "")[:30]
            close = (r.get("close_date") or "")[:10]
            cp = r.get("colppy_cuit", "")
            rs = (r.get("colppy_razon") or "")[:25]
            hs_id = r.get("hubspot_id", "")
            base_url = hubspot_deal_url(hs_id)
            url = f"[{r['id_empresa']}]({base_url})" if base_url else r["id_empresa"]
            lines.append(f"| {r['id_empresa']} | {name} | {close} | {cp} | {rs} | {url} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    if no_hubspot_cuit:
        lines.append("## NO_HUBSPOT_CUIT — Primary company exists but no CUIT in companies table")
        lines.append("")
        lines.append("| id_empresa | deal_name | Colppy DB CUIT |")
        lines.append("|------------|-----------|----------------|")
        for r in sorted(no_hubspot_cuit, key=_sort_key):
            name = (r.get("deal_name") or "")[:40]
            cp = r.get("colppy_cuit", "")
            lines.append(f"| {r['id_empresa']} | {name} | {cp} |")
        lines.append("")

    if no_colppy_cuit:
        lines.append("## NO_COLPPY_CUIT — id_empresa not in Colppy DB")
        lines.append("")
        lines.append("| id_empresa | deal_name | HubSpot primary CUIT |")
        lines.append("|------------|-----------|----------------------|")
        for r in sorted(no_colppy_cuit, key=_sort_key):
            name = (r.get("deal_name") or "")[:40]
            hs = _format_cuit(r.get("hubspot_primary_cuit"))
            lines.append(f"| {r['id_empresa']} | {name} | {hs} |")
        lines.append("")

    report = "\n".join(lines)
    print(report)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"\nReport written to: {output_path}")

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile HubSpot deal primary company CUIT with Colppy DB CUIT (alternative to facturacion.csv)"
    )
    parser.add_argument("--db", default=str(DEFAULT_HUBSPOT_DB), help="Path to facturacion_hubspot.db")
    parser.add_argument("--colppy-db", default=str(DEFAULT_COLPPY_DB), help="Path to colppy_export.db (preferred over snapshot)")
    parser.add_argument("--cuit-snapshot", default=str(DEFAULT_CUIT_SNAPSHOT), help="Path to colppy_cuit_snapshot.json (fallback)")
    parser.add_argument("--year", type=str, help="Year for timeframe filter (e.g. 2026)")
    parser.add_argument("--month", type=int, help="Month 1-12 for timeframe filter")
    parser.add_argument("--output", type=str, help="Output path for report file")
    args = parser.parse_args()

    if (args.year and not args.month) or (args.month and not args.year):
        parser.error("--year and --month must be specified together")
        return 1

    if args.year and args.month:
        if not (1 <= args.month <= 12):
            parser.error(f"--month must be between 1 and 12, got {args.month}")
        if not args.year.isdigit() or len(args.year) != 4:
            parser.error(f"--year must be a 4-digit year, got {args.year!r}")

    success = run(
        hubspot_db_path=Path(args.db),
        colppy_db_path=Path(args.colppy_db),
        cuit_snapshot_path=Path(args.cuit_snapshot),
        year=args.year,
        month=args.month,
        output_path=args.output,
    )
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
