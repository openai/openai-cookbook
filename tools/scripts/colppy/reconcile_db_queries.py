"""
Database queries for Colppy ↔ HubSpot reconciliation.
Uses context managers for safe connection handling.
"""
import calendar
import sqlite3
from pathlib import Path

ACTIVE_DEAL_STAGES = ("closedwon", "34692158")
ACTIVA_LABELS = {0: "Activa", 2: "Desactivada Falta Pago", 3: "Desactivada Usuario"}


def _get_deals_columns(conn: sqlite3.Connection) -> set[str]:
    """Get set of column names in deals table."""
    cur = conn.execute("PRAGMA table_info(deals)")
    return {r[1] for r in cur.fetchall()}


def load_colppy_first_payments(
    colppy_db_path: Path, year: str, month: int
) -> list[dict]:
    """Load Colppy first payments for given month from colppy_export.db."""
    start = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(int(year), month)[1]
    end = f"{year}-{month:02d}-{last_day}"
    with sqlite3.connect(str(colppy_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT
                p.idPago,
                p.idEmpresa,
                p.idPlan,
                pl.nombre AS plan_name,
                p.fechaPago,
                COALESCE(pd.accreditation_date, pd.payment_date) AS payment_datetime,
                p.importe,
                p.medioPago,
                p.tipoPago,
                f.CUIT AS cuit_invoicing
            FROM pago p
            LEFT JOIN plan pl ON pl.idPlan = p.idPlan
            LEFT JOIN payment_detail pd ON pd.payment_id = p.idPago AND pd.is_first_payment = 1
            LEFT JOIN facturacion f ON f.IdEmpresa = p.idEmpresa AND (f.fechaBaja IS NULL OR f.fechaBaja = '')
            WHERE p.primerPago = 1
              AND (p.estado = 1 OR (p.estado = 0 AND p.fechaTransferencia IS NOT NULL))
              AND p.fechaPago >= ?
              AND p.fechaPago < date(?, '+1 day')
            ORDER BY p.fechaPago, payment_datetime, p.idPago
            """,
            (start, end),
        )
        return [dict(r) for r in cur.fetchall()]


def load_hubspot_closed_won_from_db(
    hubspot_db_path: Path, year: str, month: int
) -> tuple[list[dict], bool, bool]:
    """Load HubSpot closed won deals for given month. Returns (rows, has_id_plan, has_fecha_primer_pago)."""
    start = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(int(year), month)[1]
    end = f"{year}-{month:02d}-{last_day}"
    with sqlite3.connect(str(hubspot_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cols = _get_deals_columns(conn)
        has_id_plan = "id_plan" in cols
        has_fecha_primer_pago = "fecha_primer_pago" in cols
        extra_cols = []
        if has_id_plan:
            extra_cols.append("id_plan")
        if has_fecha_primer_pago:
            extra_cols.append("fecha_primer_pago")
        select_cols = "id_empresa, hubspot_id, deal_name, deal_stage, amount, close_date" + (
            ", " + ", ".join(extra_cols) if extra_cols else ""
        )
        cur = conn.execute(
            f"""
            SELECT {select_cols}
            FROM deals
            WHERE deal_stage IN (?, ?)
              AND close_date >= ?
              AND close_date <= ?
            ORDER BY close_date
            """,
            (*ACTIVE_DEAL_STAGES, start, end),
        )
        rows = [dict(r) for r in cur.fetchall()]
    if not has_id_plan:
        for r in rows:
            r["id_plan"] = ""
    if not has_fecha_primer_pago:
        for r in rows:
            r["fecha_primer_pago"] = ""
    return rows, has_id_plan, has_fecha_primer_pago


def get_deal_for_id_empresa(hubspot_db_path: Path, id_empresa: str) -> dict | None:
    """Get deal for id_empresa if it exists (any month). Returns first match."""
    with sqlite3.connect(str(hubspot_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cols = _get_deals_columns(conn)
        has_id_plan = "id_plan" in cols
        has_fecha_primer_pago = "fecha_primer_pago" in cols
        extra_cols = []
        if has_id_plan:
            extra_cols.append("id_plan")
        if has_fecha_primer_pago:
            extra_cols.append("fecha_primer_pago")
        select_cols = "id_empresa, hubspot_id, deal_name, deal_stage, amount, close_date" + (
            ", " + ", ".join(extra_cols) if extra_cols else ""
        )
        cur = conn.execute(
            f"""
            SELECT {select_cols}
            FROM deals
            WHERE deal_stage IN (?, ?) AND id_empresa = ?
            LIMIT 1
            """,
            (*ACTIVE_DEAL_STAGES, str(id_empresa)),
        )
        row = cur.fetchone()
    result = dict(row) if row else None
    if result:
        if not has_id_plan:
            result["id_plan"] = ""
        if not has_fecha_primer_pago:
            result["fecha_primer_pago"] = ""
    return result


def _deals_any_stage_exists(conn: sqlite3.Connection) -> bool:
    """Check if deals_any_stage table exists."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='deals_any_stage'"
    )
    return cur.fetchone() is not None


def _get_deals_any_stage_columns(conn: sqlite3.Connection) -> set[str]:
    """Get set of column names in deals_any_stage table."""
    cur = conn.execute("PRAGMA table_info(deals_any_stage)")
    return {r[1] for r in cur.fetchall()}


def get_deal_any_stage(hubspot_db_path: Path, id_empresa: str) -> dict | None:
    """Get deal for id_empresa from deals_any_stage (any stage, for WRONG_STAGE detection)."""
    with sqlite3.connect(str(hubspot_db_path)) as conn:
        if not _deals_any_stage_exists(conn):
            return None
        conn.row_factory = sqlite3.Row
        cols = _get_deals_any_stage_columns(conn)
        has_id_plan = "id_plan" in cols
        has_fecha_primer_pago = "fecha_primer_pago" in cols
        extra_cols = []
        if has_id_plan:
            extra_cols.append("id_plan")
        if has_fecha_primer_pago:
            extra_cols.append("fecha_primer_pago")
        select_cols = "id_empresa, hubspot_id, deal_name, deal_stage, amount, close_date" + (
            ", " + ", ".join(extra_cols) if extra_cols else ""
        )
        cur = conn.execute(
            f"SELECT {select_cols} FROM deals_any_stage WHERE id_empresa = ?",
            (str(id_empresa),),
        )
        row = cur.fetchone()
        if not row:
            return None
        result = dict(row)
        if not has_id_plan:
            result["id_plan"] = ""
        if not has_fecha_primer_pago:
            result["fecha_primer_pago"] = ""
        return result


def get_empresa_activa_map(colppy_db_path: Path, id_empresas: list[str]) -> dict[str, tuple[int, str]]:
    """Get empresa activa (0=active, 2=payment failure, 3=user deactivated) for each id_empresa."""
    valid_ids = [x for x in id_empresas if str(x).isdigit()]
    if not valid_ids:
        return {}
    with sqlite3.connect(str(colppy_db_path)) as conn:
        placeholders = ",".join("?" * len(valid_ids))
        cur = conn.execute(
            f"SELECT IdEmpresa, activa FROM empresa WHERE IdEmpresa IN ({placeholders})",
            [int(x) for x in valid_ids],
        )
        out = {}
        for row in cur.fetchall():
            ie = str(row[0])
            activa = row[1] if row[1] is not None else -1
            label = ACTIVA_LABELS.get(activa, f"activa={activa}")
            out[ie] = (activa, label)
        return out


def get_colppy_first_payment(colppy_db_path: Path, id_empresa: str) -> dict | None:
    """Get first payment for id_empresa if it exists (any month)."""
    if not str(id_empresa).isdigit():
        return None
    with sqlite3.connect(str(colppy_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT p.idEmpresa, p.fechaPago, p.importe, pl.nombre AS plan_name
            FROM pago p
            LEFT JOIN plan pl ON pl.idPlan = p.idPlan
            WHERE p.primerPago = 1
              AND (p.estado = 1 OR (p.estado = 0 AND p.fechaTransferencia IS NOT NULL))
              AND p.idEmpresa = ?
            ORDER BY p.fechaPago
            LIMIT 1
            """,
            (int(id_empresa),),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_hubspot_only_colppy_status(
    colppy_db_path: Path, id_empresas: list[str]
) -> dict[str, dict]:
    """
    For each id_empresa, determine Colppy DB status.
    Returns dict: id_empresa -> {
        "reason": "NOT_IN_COLPPY" | "IN_EMPRESA_NO_PAGO" | "PRIMER_PAGO_OTHER_MONTH",
        "in_empresa": bool,
        "has_any_pago": bool,
        "primer_pago_fecha": str | None,  # YYYY-MM-DD if has primerPago
    }
    """
    valid_ids = [x for x in id_empresas if str(x).isdigit()]
    if not valid_ids:
        return {ie: {"reason": "NOT_IN_COLPPY", "in_empresa": False, "has_any_pago": False, "primer_pago_fecha": None} for ie in id_empresas}

    out = {}
    with sqlite3.connect(str(colppy_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(valid_ids))
        ids_int = [int(x) for x in valid_ids]

        # Empresa existence
        cur = conn.execute(
            f"SELECT IdEmpresa FROM empresa WHERE IdEmpresa IN ({placeholders})",
            ids_int,
        )
        in_empresa = {str(r[0]) for r in cur.fetchall()}

        # Any pago (primerPago or not)
        cur = conn.execute(
            f"SELECT idEmpresa, MIN(fechaPago) as min_fecha FROM pago WHERE idEmpresa IN ({placeholders}) GROUP BY idEmpresa",
            ids_int,
        )
        has_any_pago = {str(r[0]): (r[1][:10] if r[1] else None) for r in cur.fetchall()}

        # Primer pago (first payment) - any month
        cur = conn.execute(
            """
            SELECT p.idEmpresa, MIN(p.fechaPago) as primer_fecha
            FROM pago p
            WHERE p.primerPago = 1
              AND (p.estado = 1 OR (p.estado = 0 AND p.fechaTransferencia IS NOT NULL))
              AND p.idEmpresa IN ({})
            GROUP BY p.idEmpresa
            """.format(placeholders),
            ids_int,
        )
        primer_pago = {str(r[0]): (r[1][:10] if r[1] else None) for r in cur.fetchall()}

    for ie in id_empresas:
        in_e = ie in in_empresa
        has_pago = ie in has_any_pago
        primer_fecha = primer_pago.get(ie)

        if not in_e:
            reason = "NOT_IN_COLPPY"
        elif not has_pago:
            reason = "IN_EMPRESA_NO_PAGO"
        elif primer_fecha:
            reason = "PRIMER_PAGO_OTHER_MONTH"
        else:
            reason = "IN_EMPRESA_PAGO_NO_PRIMER"

        out[ie] = {
            "reason": reason,
            "in_empresa": in_e,
            "has_any_pago": has_pago,
            "primer_pago_fecha": primer_fecha,
        }
    return out


def get_billing_crm_to_colppy_mapping(hubspot_db_path: Path) -> dict[str, str]:
    """From facturacion: same customer_cuit, CRM id (Pendiente) -> Colppy id (active plan).

    Assumption: When a CUIT has multiple CRM ids (Pendiente) and multiple Colppy ids (active),
    each CRM id maps to the first Colppy id found. Typical case: one Pendiente and one active per CUIT.
    """
    with sqlite3.connect(str(hubspot_db_path)) as conn:
        cur = conn.execute(
            """
            SELECT customer_cuit, id_empresa, plan
            FROM facturacion
            WHERE id_empresa IS NOT NULL AND id_empresa != ''
            """
        )
        rows = cur.fetchall()
    by_cuit = {}
    for cuit, id_emp, plan in rows:
        cuit = (cuit or "").replace("-", "").replace(" ", "")
        if len(cuit) != 11:
            continue
        if cuit not in by_cuit:
            by_cuit[cuit] = []
        by_cuit[cuit].append((str(id_emp), (plan or "").strip()))
    mapping = {}
    for cuit, items in by_cuit.items():
        colppy_ids = [ie for ie, plan in items if plan and "Pendiente" not in plan]
        crm_ids = [ie for ie, plan in items if plan and "Pendiente" in plan]
        for crm in crm_ids:
            for colp in colppy_ids:
                mapping[crm] = colp
                break
    return mapping
