"""
Reconciliation logging — persist reconciliation run summaries and record-level ids to SQLite.

Stores each run with metrics and id lists so you can compare variations between data refreshes
and see which records were fixed, new, or regressed.

Usage:
    from tools.utils.reconciliation_logger import log_reconciliation, get_reconciliation_history

    log_reconciliation(
        db_path="tools/data/facturacion_hubspot.db",
        script="reconcile_colppy_hubspot",
        reconciliation_type="colppy_first_payments_hubspot_closedwon",
        period="YYYY-MM",  # e.g. 2026-02, pass from script args
        match_count=len(match_ids),
        source_a_total=len(colppy_ids),
        source_b_total=len(hubspot_ids),
        source_a_only_count=len(colppy_only),
        source_b_only_count=len(hubspot_only),
        match_ids=sorted(match_ids),
        source_a_only_ids=sorted(colppy_only),
        source_b_only_ids=sorted(hubspot_only),
        source_metadata={"colppy_exported_at": "..."},  # from snapshot metadata if available
    )
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

ARGENTINA_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

DEFAULT_DB = "tools/data/facturacion_hubspot.db"

RECONCILIATION_LOGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS reconciliation_logs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT NOT NULL,
    script              TEXT NOT NULL,
    reconciliation_type TEXT NOT NULL,
    period              TEXT,
    match_count         INTEGER NOT NULL,
    source_a_total      INTEGER NOT NULL,
    source_b_total      INTEGER NOT NULL,
    source_a_only_count INTEGER NOT NULL,
    source_b_only_count INTEGER NOT NULL,
    match_ids           TEXT,
    source_a_only_ids   TEXT,
    source_b_only_ids   TEXT,
    source_metadata     TEXT,
    extra               TEXT
);
CREATE INDEX IF NOT EXISTS idx_recon_logs_script ON reconciliation_logs(script);
CREATE INDEX IF NOT EXISTS idx_recon_logs_type ON reconciliation_logs(reconciliation_type);
CREATE INDEX IF NOT EXISTS idx_recon_logs_timestamp ON reconciliation_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_recon_logs_period ON reconciliation_logs(period);
"""


def _init_table(conn: sqlite3.Connection) -> None:
    """Ensure reconciliation_logs table exists and has record-level columns."""
    conn.executescript(RECONCILIATION_LOGS_SCHEMA)
    # Migrate: add record-level columns if missing
    try:
        cur = conn.execute("PRAGMA table_info(reconciliation_logs)")
        cols = {row[1] for row in cur.fetchall()}
        if "match_ids" not in cols:
            conn.execute("ALTER TABLE reconciliation_logs ADD COLUMN match_ids TEXT")
        if "source_a_only_ids" not in cols:
            conn.execute("ALTER TABLE reconciliation_logs ADD COLUMN source_a_only_ids TEXT")
        if "source_b_only_ids" not in cols:
            conn.execute("ALTER TABLE reconciliation_logs ADD COLUMN source_b_only_ids TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def log_reconciliation(
    db_path: str,
    script: str,
    reconciliation_type: str,
    period: str | None,
    match_count: int,
    source_a_total: int,
    source_b_total: int,
    source_a_only_count: int,
    source_b_only_count: int,
    source_metadata: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    match_ids: list[str] | None = None,
    source_a_only_ids: list[str] | None = None,
    source_b_only_ids: list[str] | None = None,
) -> int:
    """
    Log a reconciliation run to SQLite.

    Returns the inserted row id.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    _init_table(conn)
    ts = datetime.now(ARGENTINA_TZ).isoformat()
    meta_json = json.dumps(source_metadata) if source_metadata else None
    extra_json = json.dumps(extra) if extra else None
    match_ids_json = json.dumps(match_ids) if match_ids is not None else None
    a_only_json = json.dumps(source_a_only_ids) if source_a_only_ids is not None else None
    b_only_json = json.dumps(source_b_only_ids) if source_b_only_ids is not None else None
    cur = conn.execute(
        """
        INSERT INTO reconciliation_logs (
            timestamp, script, reconciliation_type, period,
            match_count, source_a_total, source_b_total,
            source_a_only_count, source_b_only_count,
            match_ids, source_a_only_ids, source_b_only_ids,
            source_metadata, extra
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts,
            script,
            reconciliation_type,
            period,
            match_count,
            source_a_total,
            source_b_total,
            source_a_only_count,
            source_b_only_count,
            match_ids_json,
            a_only_json,
            b_only_json,
            meta_json,
            extra_json,
        ),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id or 0


def get_reconciliation_history(
    db_path: str,
    script: str | None = None,
    reconciliation_type: str | None = None,
    period: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Fetch reconciliation history for progress display and variation analysis.

    Returns rows ordered by timestamp DESC.
    """
    path = Path(db_path)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    where = []
    params = []
    if script:
        where.append("script = ?")
        params.append(script)
    if reconciliation_type:
        where.append("reconciliation_type = ?")
        params.append(reconciliation_type)
    if period:
        where.append("period = ?")
        params.append(period)
    clause = " AND ".join(where) if where else "1=1"
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT id, timestamp, script, reconciliation_type, period,
               match_count, source_a_total, source_b_total,
               source_a_only_count, source_b_only_count,
               match_ids, source_a_only_ids, source_b_only_ids,
               source_metadata, extra
        FROM reconciliation_logs
        WHERE {clause}
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("source_metadata"):
            try:
                d["source_metadata"] = json.loads(d["source_metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        if d.get("extra"):
            try:
                d["extra"] = json.loads(d["extra"])
            except (json.JSONDecodeError, TypeError):
                pass
        if d.get("match_ids"):
            try:
                d["match_ids"] = json.loads(d["match_ids"])
            except (json.JSONDecodeError, TypeError):
                d["match_ids"] = []
        if d.get("source_a_only_ids"):
            try:
                d["source_a_only_ids"] = json.loads(d["source_a_only_ids"])
            except (json.JSONDecodeError, TypeError):
                d["source_a_only_ids"] = []
        if d.get("source_b_only_ids"):
            try:
                d["source_b_only_ids"] = json.loads(d["source_b_only_ids"])
            except (json.JSONDecodeError, TypeError):
                d["source_b_only_ids"] = []
        out.append(d)
    return out


def get_reconciliation_diff(
    db_path: str,
    script: str | None = None,
    reconciliation_type: str | None = None,
    period: str | None = None,
) -> dict[str, Any] | None:
    """
    Compare the latest run with the previous run. Returns record-level changes.

    Each record gets a status: fixed | new | unchanged | regression
    - fixed: was in source_a_only or source_b_only before, now in match
    - new: id didn't exist in previous run
    - unchanged: same bucket as before
    - regression: was in match before, now in source_a_only or source_b_only
    """
    rows = get_reconciliation_history(db_path, script, reconciliation_type, period, limit=2)
    if len(rows) < 2:
        return None
    curr, prev = rows[0], rows[1]
    curr_match = set(curr.get("match_ids") or [])
    curr_a = set(curr.get("source_a_only_ids") or [])
    curr_b = set(curr.get("source_b_only_ids") or [])
    prev_match = set(prev.get("match_ids") or [])
    prev_a = set(prev.get("source_a_only_ids") or [])
    prev_b = set(prev.get("source_b_only_ids") or [])
    prev_all = prev_match | prev_a | prev_b

    def _status(id_: str, bucket: str) -> str:
        if bucket == "match":
            if id_ in prev_match:
                return "unchanged"
            if id_ in prev_a or id_ in prev_b:
                return "fixed"
            return "new"
        if bucket == "source_a_only":
            if id_ in prev_match:
                return "regression"
            if id_ in prev_a:
                return "unchanged"
            return "new"
        if bucket == "source_b_only":
            if id_ in prev_match:
                return "regression"
            if id_ in prev_b:
                return "unchanged"
            return "new"
        return "unknown"

    records = []
    for id_ in sorted(curr_match, key=lambda x: int(x) if x.isdigit() else 0):
        records.append({"id": id_, "bucket": "match", "status": _status(id_, "match")})
    for id_ in sorted(curr_a, key=lambda x: int(x) if x.isdigit() else 0):
        records.append({"id": id_, "bucket": "source_a_only", "status": _status(id_, "source_a_only")})
    for id_ in sorted(curr_b, key=lambda x: int(x) if x.isdigit() else 0):
        records.append({"id": id_, "bucket": "source_b_only", "status": _status(id_, "source_b_only")})

    removed = prev_all - (curr_match | curr_a | curr_b)
    prev_has_ids = bool(prev_match or prev_a or prev_b)

    return {
        "current_run": curr.get("timestamp"),
        "previous_run": prev.get("timestamp"),
        "records": records,
        "removed_ids": sorted(removed, key=lambda x: int(x) if x.isdigit() else 0),
        "prev_has_record_ids": prev_has_ids,
        "summary": {
            "fixed": sum(1 for r in records if r["status"] == "fixed"),
            "new": sum(1 for r in records if r["status"] == "new"),
            "unchanged": sum(1 for r in records if r["status"] == "unchanged"),
            "regression": sum(1 for r in records if r["status"] == "regression"),
            "removed": len(removed),
        },
    }
