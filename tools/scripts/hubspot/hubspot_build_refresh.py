"""
Refresh deals-only logic for facturacion–HubSpot mapping.
"""
import calendar
import sqlite3
from pathlib import Path

from .hubspot_build_fetchers import (
    ACTIVE_DEAL_STAGES,
    fetch_deals_by_id_empresa,
    fetch_deals_closed_in_month,
)
from .hubspot_build_sqlite import (
    _get_deal_fecha_primer_pago,
    _get_deal_id_plan,
    _ensure_deals_has_fecha_primer_pago,
    _ensure_deals_has_id_plan,
    _ensure_deals_any_stage_has_fecha_primer_pago,
    _ensure_deals_any_stage_has_id_plan,
)


def run_refresh_deals_only(
    db_path: Path,
    year: str,
    month: int,
    fetch_wrong_stage: bool,
    colppy_db_path: Path,
) -> int:
    """
    Refresh deals table for given month. Optionally populate deals_any_stage.
    Returns 0 on success, 1 on error.
    """
    from tools.hubspot_api.client import get_hubspot_client
    from tools.utils.hubspot_refresh_logger import log_hubspot_refresh

    client = get_hubspot_client()
    month_key = f"{year}-{month:02d}"
    start = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(int(year), month)[1]
    end = f"{year}-{month:02d}-{last_day}"

    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS deals (
                id_empresa TEXT PRIMARY KEY, hubspot_id TEXT, deal_name TEXT, deal_stage TEXT,
                amount TEXT, close_date TEXT, id_plan TEXT, fecha_primer_pago TEXT
            );
        """)
        _ensure_deals_has_id_plan(conn)
        _ensure_deals_has_fecha_primer_pago(conn)

        old_rows = conn.execute(
            """SELECT id_empresa, deal_name, amount, close_date, id_plan, fecha_primer_pago FROM deals
               WHERE close_date >= ? AND close_date <= ?""",
            (start, end),
        ).fetchall()
    old_by_id = {
        str(r[0]): {
            "deal_name": r[1],
            "amount": r[2],
            "close_date": (r[3] or "")[:10],
            "id_plan": (r[4] or "").strip(),
            "fecha_primer_pago": (r[5] or "").strip()[:10] if len(r) > 5 else "",
        }
        for r in old_rows
    }

    print(f"Fetching HubSpot closed won deals for {month_key}...")
    id_to_deal = fetch_deals_closed_in_month(client, year, month)
    print(f"  Found: {len(id_to_deal):,} deals")

    new_by_id = {}
    for id_emp, d in id_to_deal.items():
        if not d:
            continue
        props = d.get("properties", {})
        new_by_id[id_emp] = {
            "deal_name": props.get("dealname", ""),
            "amount": str(props.get("amount", "")),
            "close_date": (props.get("closedate") or "")[:10],
            "id_plan": _get_deal_id_plan(props),
            "fecha_primer_pago": _get_deal_fecha_primer_pago(props),
        }

    old_ids = set(old_by_id.keys())
    new_ids = set(new_by_id.keys())
    added_ids = sorted(new_ids - old_ids, key=lambda x: int(x) if str(x).isdigit() else 0)
    removed_ids = sorted(old_ids - new_ids, key=lambda x: int(x) if str(x).isdigit() else 0)
    updated_ids = [
        id_emp for id_emp in sorted(old_ids & new_ids, key=lambda x: int(x) if str(x).isdigit() else 0)
        if old_by_id[id_emp] != new_by_id[id_emp]
    ]

    with sqlite3.connect(str(db_path)) as conn:
        if removed_ids:
            placeholders = ",".join("?" * len(removed_ids))
            conn.execute(f"DELETE FROM deals WHERE id_empresa IN ({placeholders})", removed_ids)
            conn.commit()

        for id_emp, d in id_to_deal.items():
            if not d:
                continue
            props = d.get("properties", {})
            conn.execute(
                """INSERT OR REPLACE INTO deals (id_empresa, hubspot_id, deal_name, deal_stage, amount, close_date, id_plan, fecha_primer_pago)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    id_emp,
                    d.get("id", ""),
                    props.get("dealname", ""),
                    props.get("dealstage", ""),
                    props.get("amount", ""),
                    (props.get("closedate") or "")[:10],
                    _get_deal_id_plan(props),
                    _get_deal_fecha_primer_pago(props),
                ),
            )
        conn.commit()

        if fetch_wrong_stage:
            # Colppy-only: first payments this month without closed-won
            colppy_only = set()
            if colppy_db_path.exists():
                with sqlite3.connect(str(colppy_db_path)) as colppy_db_conn:
                    cur = colppy_db_conn.execute(
                        """
                        SELECT DISTINCT p.idEmpresa FROM pago p
                        WHERE p.primerPago = 1
                          AND (p.estado = 1 OR (p.estado = 0 AND p.fechaTransferencia IS NOT NULL))
                          AND p.fechaPago >= ? AND p.fechaPago < date(?, '+1 day')
                        """,
                        (start, end),
                    )
                    colppy_ids = {str(r[0]) for r in cur.fetchall()}
                closed_won_ids = set(id_to_deal.keys())
                colppy_only = colppy_ids - closed_won_ids

            # Facturacion ids without deals: match by id_empresa regardless of stage
            facturacion_no_deal = set()
            cur = conn.execute(
                """SELECT DISTINCT f.id_empresa FROM facturacion f
                   LEFT JOIN deals d ON f.id_empresa = d.id_empresa
                   WHERE d.id_empresa IS NULL AND f.id_empresa != '' AND f.id_empresa IS NOT NULL
                     AND f.id_empresa GLOB '[0-9]*'"""
            )
            facturacion_no_deal = {str(r[0]) for r in cur.fetchall()}

            ids_to_fetch = colppy_only | facturacion_no_deal
            if ids_to_fetch:
                print(f"  Fetching deals (any stage) for {len(ids_to_fetch):,} id_empresas (Colppy-only + facturacion no deal)...")
                wrong_stage_deals = fetch_deals_by_id_empresa(client, ids_to_fetch, delay=0.25)
                wrong_stage_filtered = {
                    ie: d for ie, d in wrong_stage_deals.items()
                    if (d.get("properties", {}).get("dealstage") or "").strip() not in ACTIVE_DEAL_STAGES
                }
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS deals_any_stage (
                        id_empresa TEXT PRIMARY KEY, hubspot_id TEXT, deal_name TEXT, deal_stage TEXT,
                        amount TEXT, close_date TEXT, id_plan TEXT, fecha_primer_pago TEXT
                    );
                """)
                _ensure_deals_any_stage_has_id_plan(conn)
                _ensure_deals_any_stage_has_fecha_primer_pago(conn)
                conn.execute("DELETE FROM deals_any_stage")
                conn.commit()
                for id_emp, d in wrong_stage_filtered.items():
                    if not d:
                        continue
                    props = d.get("properties", {})
                    conn.execute(
                        """INSERT OR REPLACE INTO deals_any_stage (id_empresa, hubspot_id, deal_name, deal_stage, amount, close_date, id_plan, fecha_primer_pago)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            id_emp,
                            d.get("id", ""),
                            props.get("dealname", ""),
                            props.get("dealstage", ""),
                            props.get("amount", ""),
                            (props.get("closedate") or "")[:10],
                            _get_deal_id_plan(props),
                            _get_deal_fecha_primer_pago(props),
                        ),
                    )
                conn.commit()
                print(f"  Stored {len(wrong_stage_filtered):,} deals with wrong stage in deals_any_stage")

    log_hubspot_refresh(
        db_path=str(db_path),
        period=month_key,
        deal_count=len(id_to_deal),
        added_count=len(added_ids),
        updated_count=len(updated_ids),
        removed_count=len(removed_ids),
        added_ids=added_ids,
        updated_ids=updated_ids,
        removed_ids=removed_ids,
        source_metadata={"source": "hubspot_api", "filter": "closedate_in_month"},
    )

    print(f"  Upserted {len(id_to_deal):,} deals into {db_path}")
    if added_ids or updated_ids or removed_ids:
        print(f"  Evolution: +{len(added_ids)} added, ~{len(updated_ids)} updated, -{len(removed_ids)} removed")
        if added_ids:
            print(f"    Added: {', '.join(added_ids[:10])}{'...' if len(added_ids) > 10 else ''}")
        if removed_ids:
            print(f"    Removed: {', '.join(removed_ids[:10])}{'...' if len(removed_ids) > 10 else ''}")
    print(f"  Refresh logged to hubspot_refresh_logs")
    return 0
