#!/usr/bin/env python3
"""
Edit Log DB — Centralized logging of HubSpot/data modifications to SQLite.

All scripts that modify HubSpot or local data should log to the edit_logs table
in facturacion_hubspot.db for audit and traceability.

Usage:
    from tools.scripts.hubspot.edit_log_db import ensure_edit_log_table, log_edit

    conn = sqlite3.connect(db_path)
    ensure_edit_log_table(conn)
    log_edit(conn, script="fix_deal_associations", action="group_1", outcome="fixed",
             detail="cuit_ok", deal_id="123", deal_name="Deal X", ...)
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

EDIT_LOGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS edit_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    script          TEXT NOT NULL,
    action          TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    detail          TEXT,
    deal_id         TEXT,
    deal_name       TEXT,
    deal_url        TEXT,
    company_id      TEXT,
    company_name    TEXT,
    company_url     TEXT,
    company_id_secondary TEXT,
    customer_cuit   TEXT
);

CREATE INDEX IF NOT EXISTS idx_edit_logs_script ON edit_logs(script);
CREATE INDEX IF NOT EXISTS idx_edit_logs_timestamp ON edit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_edit_logs_deal ON edit_logs(deal_id);
"""


def ensure_edit_log_table(conn: sqlite3.Connection) -> None:
    """Create edit_logs table and indexes if they do not exist."""
    conn.executescript(EDIT_LOGS_SCHEMA)
    conn.commit()


def log_edit(
    conn: sqlite3.Connection,
    script: str,
    action: str,
    outcome: str,
    detail: str = "",
    deal_id: str = "",
    deal_name: str = "",
    deal_url: str = "",
    company_id: str = "",
    company_name: str = "",
    company_url: str = "",
    company_id_secondary: str = "",
    customer_cuit: str = "",
) -> None:
    """
    Insert one row into edit_logs.

    Args:
        conn: SQLite connection
        script: Script name (e.g. fix_deal_associations, merge_duplicate_companies)
        action: Action type (e.g. group_1, group_2, merge)
        outcome: Result (fixed, failed, skipped, success)
        detail: Additional detail (e.g. cuit_ok, cuit_patched)
        deal_id, deal_name, deal_url: Deal fields
        company_id, company_name, company_url: Primary company fields
        company_id_secondary: For merge — the archived company ID
        customer_cuit: Billing CUIT
    """
    ensure_edit_log_table(conn)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT INTO edit_logs (
            timestamp, script, action, outcome, detail,
            deal_id, deal_name, deal_url,
            company_id, company_name, company_url, company_id_secondary,
            customer_cuit
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts,
            script,
            action,
            outcome,
            (detail or "")[:500],
            (deal_id or "")[:50],
            (deal_name or "")[:200],
            (deal_url or "")[:500],
            (company_id or "")[:50],
            (company_name or "")[:200],
            (company_url or "")[:500],
            (company_id_secondary or "")[:50],
            (customer_cuit or "")[:20],
        ),
    )
    conn.commit()


def log_edits_batch(conn: sqlite3.Connection, script: str, action: str, outcomes: list[dict]) -> int:
    """
    Insert multiple rows from a list of outcome dicts.
    Dict keys: deal_id, deal_name, billing_id, billing_name, customer_cuit, outcome, detail.
    Optional: deal_url, company_url (or derived from IDs).
    Returns number of rows inserted.
    """
    ensure_edit_log_table(conn)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _hubspot_deal_url(did: str) -> str:
        return f"https://app.hubspot.com/contacts/19877595/deal/{did}" if did else ""

    def _hubspot_company_url(cid: str) -> str:
        return f"https://app.hubspot.com/contacts/19877595/company/{cid}" if cid else ""

    rows = []
    for r in outcomes:
        deal_id = str(r.get("deal_id", ""))
        billing_id = str(r.get("billing_id", ""))
        rows.append((
            ts,
            script,
            action,
            r.get("outcome", ""),
            (r.get("detail") or "")[:500],
            deal_id[:50],
            ((r.get("deal_name") or "")[:200]),
            r.get("deal_url") or _hubspot_deal_url(deal_id),
            billing_id[:50],
            ((r.get("billing_name") or "")[:200]),
            r.get("company_url") or _hubspot_company_url(billing_id),
            "",
            (r.get("customer_cuit") or "")[:20],
        ))

    conn.executemany(
        """
        INSERT INTO edit_logs (
            timestamp, script, action, outcome, detail,
            deal_id, deal_name, deal_url,
            company_id, company_name, company_url, company_id_secondary,
            customer_cuit
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return len(rows)
