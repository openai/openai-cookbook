"""
HubSpot refresh logging — persist deal refresh evolution to SQLite.

Stores each --refresh-deals-only run with before/after comparison so you can see
what changed in HubSpot even when Colppy staging is unavailable.

Usage:
    from tools.utils.hubspot_refresh_logger import (
        log_hubspot_refresh,
        get_hubspot_refresh_history,
        log_deal_associations_refresh,
        get_last_deal_associations_refresh,
    )

    log_hubspot_refresh(
        db_path="tools/data/facturacion_hubspot.db",
        period="2026-02",
        deal_count=39,
        added_ids=["123", "456"],
        updated_ids=["789"],
        removed_ids=["111"],
    )
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

ARGENTINA_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

HUBSPOT_REFRESH_LOGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS hubspot_refresh_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    period          TEXT NOT NULL,
    deal_count      INTEGER NOT NULL,
    added_count     INTEGER NOT NULL,
    updated_count   INTEGER NOT NULL,
    removed_count   INTEGER NOT NULL,
    added_ids       TEXT,
    updated_ids     TEXT,
    removed_ids     TEXT,
    source_metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_hubspot_refresh_period ON hubspot_refresh_logs(period);
CREATE INDEX IF NOT EXISTS idx_hubspot_refresh_timestamp ON hubspot_refresh_logs(timestamp);
"""

DEAL_ASSOCIATIONS_REFRESH_SCHEMA = """
CREATE TABLE IF NOT EXISTS hubspot_deal_associations_refresh_logs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT NOT NULL,
    total_associations  INTEGER NOT NULL,
    unique_deals        INTEGER NOT NULL,
    unique_companies    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_deal_assoc_refresh_ts ON hubspot_deal_associations_refresh_logs(timestamp);
"""


def _init_table(conn: sqlite3.Connection) -> None:
    conn.executescript(HUBSPOT_REFRESH_LOGS_SCHEMA)
    conn.commit()


def _init_deal_associations_table(conn: sqlite3.Connection) -> None:
    conn.executescript(DEAL_ASSOCIATIONS_REFRESH_SCHEMA)
    conn.commit()


def log_deal_associations_refresh(
    db_path: str,
    total_associations: int,
    unique_deals: int,
    unique_companies: int,
) -> int:
    """
    Log a deal_associations populate run. Call from populate_deal_associations.py
    after successful refresh so you can see when associations were last synced.

    Returns the inserted row id.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    _init_deal_associations_table(conn)
    ts = datetime.now(ARGENTINA_TZ).isoformat()
    cur = conn.execute(
        """
        INSERT INTO hubspot_deal_associations_refresh_logs
        (timestamp, total_associations, unique_deals, unique_companies)
        VALUES (?, ?, ?, ?)
        """,
        (ts, total_associations, unique_deals, unique_companies),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id or 0


def get_last_deal_associations_refresh(db_path: str) -> Optional[Dict[str, Any]]:
    """Return the most recent deal_associations refresh record, or None."""
    path = Path(db_path)
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    conn.executescript(DEAL_ASSOCIATIONS_REFRESH_SCHEMA)
    row = conn.execute(
        """
        SELECT timestamp, total_associations, unique_deals, unique_companies
        FROM hubspot_deal_associations_refresh_logs
        ORDER BY timestamp DESC LIMIT 1
        """
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "timestamp": row[0],
        "total_associations": row[1],
        "unique_deals": row[2],
        "unique_companies": row[3],
    }


def log_hubspot_refresh(
    db_path: str,
    period: str,
    deal_count: int,
    added_count: int = 0,
    updated_count: int = 0,
    removed_count: int = 0,
    added_ids: Optional[List[str]] = None,
    updated_ids: Optional[List[str]] = None,
    removed_ids: Optional[List[str]] = None,
    source_metadata: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Log a HubSpot deals refresh run to SQLite.

    Returns the inserted row id.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    _init_table(conn)
    ts = datetime.now(ARGENTINA_TZ).isoformat()
    added_json = json.dumps(added_ids) if added_ids is not None else None
    updated_json = json.dumps(updated_ids) if updated_ids is not None else None
    removed_json = json.dumps(removed_ids) if removed_ids is not None else None
    meta_json = json.dumps(source_metadata) if source_metadata else None
    cur = conn.execute(
        """
        INSERT INTO hubspot_refresh_logs (
            timestamp, period, deal_count,
            added_count, updated_count, removed_count,
            added_ids, updated_ids, removed_ids,
            source_metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts,
            period,
            deal_count,
            added_count,
            updated_count,
            removed_count,
            added_json,
            updated_json,
            removed_json,
            meta_json,
        ),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id or 0


def get_hubspot_refresh_history(
    db_path: str,
    period: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Fetch HubSpot refresh history for evolution display.

    Returns rows ordered by timestamp DESC.
    """
    path = Path(db_path)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    where = "period = ?" if period else "1=1"
    params = [period] if period else []
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT id, timestamp, period, deal_count,
               added_count, updated_count, removed_count,
               added_ids, updated_ids, removed_ids, source_metadata
        FROM hubspot_refresh_logs
        WHERE {where}
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        for key in ("added_ids", "updated_ids", "removed_ids"):
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    d[key] = []
        if d.get("source_metadata"):
            try:
                d["source_metadata"] = json.loads(d["source_metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        out.append(d)
    return out
