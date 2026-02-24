#!/usr/bin/env python3
"""
Export Colppy id_empresa → CUIT Snapshot
=========================================
Reads from colppy_export.db and exports id_empresa → CUIT mapping.
Source: Colppy DB (facturacion.CUIT = customer/billing CUIT, empresa.CUIT = fallback).
Different from billing facturacion.csv — this is Colppy DB as source of truth for CUIT.

Use for Colppy-based CUIT reconciliation (Colppy DB vs HubSpot primary company CUIT).

Usage:
  python tools/scripts/colppy/export_colppy_cuit_snapshot.py
  python tools/scripts/colppy/export_colppy_cuit_snapshot.py --output plugins/colppy-ceo-assistant/docs/colppy_cuit_snapshot.json
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DB = REPO_ROOT / "tools/data/colppy_export.db"
DEFAULT_OUTPUT = REPO_ROOT / "plugins/colppy-ceo-assistant/docs/colppy_cuit_snapshot.json"

from tools.scripts.hubspot.hubspot_build_fetchers import format_cuit_display, normalize_cuit


def _normalize_cuit_str(raw: str) -> str:
    """Normalize CUIT to 11 digits or empty string."""
    n = normalize_cuit(raw or "")
    return n or ""


def query_cuit_by_id_empresa(db_path: Path) -> list[dict]:
    """
    Get id_empresa → CUIT from Colppy DB.
    Primary: facturacion.CUIT (customer/billing CUIT, fechaBaja IS NULL).
    Fallback: empresa.CUIT for id_empresas not in active facturacion.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        # 1. From facturacion (active billing)
        cur = conn.execute(
            """
            SELECT f.IdEmpresa AS id_empresa, f.CUIT AS cuit_raw, f.razonSocial
            FROM facturacion f
            WHERE (f.fechaBaja IS NULL OR f.fechaBaja = '' OR f.fechaBaja = '0000-00-00')
              AND f.IdEmpresa IS NOT NULL AND f.IdEmpresa != 0 AND f.IdEmpresa != ''
            """
        )
        by_facturacion = {}
        for r in cur.fetchall():
            ie = str(r["id_empresa"] or "").strip()
            if not ie:
                continue
            cuit = _normalize_cuit_str(r["cuit_raw"] or "")
            if cuit:
                by_facturacion[ie] = {
                    "cuit": cuit,
                    "cuit_display": format_cuit_display(cuit),
                    "source": "facturacion",
                    "razon_social": (r["razonSocial"] or "").strip()[:80],
                }

        # 2. From empresa (fallback for id_empresas not in facturacion)
        cur = conn.execute(
            """
            SELECT e.IdEmpresa AS id_empresa, e.CUIT AS cuit_raw, e.Nombre AS razon_social
            FROM empresa e
            WHERE e.IdEmpresa IS NOT NULL AND e.IdEmpresa != 0 AND e.IdEmpresa != ''
            """
        )
        for r in cur.fetchall():
            ie = str(r["id_empresa"] or "").strip()
            if not ie or ie in by_facturacion:
                continue
            cuit = _normalize_cuit_str(r["cuit_raw"] or "")
            if cuit:
                by_facturacion[ie] = {
                    "cuit": cuit,
                    "cuit_display": format_cuit_display(cuit),
                    "source": "empresa",
                    "razon_social": (r["razon_social"] or "").strip()[:80],
                }

        return [{"id_empresa": ie, **data} for ie, data in sorted(by_facturacion.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0)]


def run_export(db_path: Path, output_path: Path, quiet: bool = False) -> None:
    """
    Export id_empresa → CUIT snapshot to JSON.

    Args:
        db_path: Path to colppy_export.db.
        output_path: Path for output JSON file.
        quiet: If True, suppress print output.

    Side effects:
        Writes JSON to output_path. Exits with code 1 if db_path does not exist.
    """
    if not db_path.exists():
        print(f"Error: SQLite not found at {db_path}")
        print("Run export_colppy_to_sqlite.py first (requires Colppy MySQL/VPN).")
        sys.exit(1)

    rows = query_cuit_by_id_empresa(db_path)
    now = datetime.utcnow()
    snapshot = {
        "metadata": {
            "exported_at": now.isoformat() + "Z",
            "source": "colppy_export.db",
            "source_type": "colppy_db",
            "description": "id_empresa → CUIT from Colppy DB. Different from billing facturacion.csv — use for Colppy-based CUIT reconciliation vs HubSpot.",
            "id_empresa_count": len(rows),
        },
        "cuit_by_id_empresa": {r["id_empresa"]: {k: v for k, v in r.items() if k != "id_empresa"} for r in rows},
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    if not quiet:
        print(f"Exported {len(rows)} id_empresa → CUIT mappings from Colppy DB")
        print(f"Saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Export Colppy id_empresa → CUIT snapshot to JSON"
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to colppy_export.db")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path")
    parser.add_argument("--quiet", action="store_true", help="Suppress output")
    args = parser.parse_args()
    run_export(args.db, args.output, args.quiet)


if __name__ == "__main__":
    main()
