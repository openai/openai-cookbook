#!/usr/bin/env python3
"""
Colppy–HubSpot Reconciliation MCP Server
=======================================
Exposes reconciliation tools via Model Context Protocol for use in Cursor, Claude Desktop, etc.

Tools:
- refresh_colppy_db: Refresh Colppy data from MySQL (requires VPN)
- refresh_hubspot_deals: Refresh HubSpot closed-won deals (single month or multi-year)
- populate_deal_associations: Sync deal–company associations
- run_reconciliation: Run Colppy ↔ HubSpot reconciliation report
- run_full_refresh: Orchestrate Colppy + HubSpot refresh + reconciliation for a month

Usage:
    uv run mcp_reconciliation_server.py
    # Or: python -m mcp_reconciliation_server (with mcp[cli] installed)

Cursor config (~/.cursor/mcp.json):
    "reconciliation": {
      "command": "uv",
      "args": ["run", "tools/scripts/reconciliation/mcp_reconciliation_server.py"],
      "cwd": "/path/to/openai-cookbook"
    }
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "tools" / ".env")

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "tools" / ".env")


def _run_script(args: list[str], timeout: int = 600) -> tuple[int, str, str]:
    """Run a Python script from repo root. Returns (exit_code, stdout, stderr)."""
    cmd = [sys.executable] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else (e.stdout.decode(errors="replace") if e.stdout else "")
        err = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode(errors="replace") if e.stderr else "")
        return -1, out, f"Process timed out after {timeout}s. {err}"
    except FileNotFoundError as e:
        return -1, "", f"Script not found: {e}"


def _validate_year_month(year: int, month: int) -> str | None:
    """Return error message or None if valid."""
    if not (1 <= month <= 12):
        return f"month must be 1–12, got {month}"
    if not (2000 <= year <= 2100):
        return f"year must be 2000–2100, got {year}"
    return None


def _format_output(exit_code: int, stdout: str, stderr: str) -> str:
    """Format subprocess output for MCP tool response."""
    parts = []
    if stdout:
        parts.append(stdout.strip())
    if stderr:
        parts.append(f"stderr:\n{stderr.strip()}")
    parts.append(f"\nExit code: {exit_code}")
    return "\n\n".join(parts)


# FastMCP must be imported after we ensure REPO_ROOT is on path (for tools/.env)
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("colppy-reconciliation")


@mcp.tool()
def refresh_colppy_db(incremental: bool = False) -> str:
    """
    Refresh Colppy database (colppy_export.db) from MySQL.
    Requires VPN to reach Colppy production DB.
    Use incremental=True for faster sync of recent pago/facturacion changes.
    """
    args = ["tools/scripts/colppy/export_colppy_to_sqlite.py"]
    if incremental:
        args.append("--incremental")
    code, out, err = _run_script(args, timeout=300)
    return _format_output(code, out, err)


@mcp.tool()
def refresh_hubspot_deals(
    year: int = 2026,
    month: int = 2,
    fetch_wrong_stage: bool = True,
    years: str | None = None,
) -> str:
    """
    Refresh HubSpot closed-won deals for facturacion mapping.
    Use year+month for single month (default 2026-02), or years (e.g. "2025 2026") for multi-year.
    fetch_wrong_stage populates deals_any_stage for WRONG_STAGE / Colppy-only detection.
    """
    args = [
        "tools/scripts/hubspot/build_facturacion_hubspot_mapping.py",
        "--refresh-deals-only",
    ]
    if years and years.strip():
        args.extend(["--years"] + years.strip().split())
    else:
        args.extend(["--year", str(year), "--month", str(month)])
    if fetch_wrong_stage:
        args.append("--fetch-wrong-stage")
    # Multi-year can take ~1 hour; single month ~2–3 min
    timeout = 7200 if years else 300
    code, out, err = _run_script(args, timeout=timeout)
    return _format_output(code, out, err)


@mcp.tool()
def populate_deal_associations() -> str:
    """
    Populate deal–company associations in facturacion_hubspot.db.
    Required before CUIT reconciliation. Uses batch API with null-safe handling.
    """
    args = ["tools/scripts/hubspot/populate_deal_associations.py", "--batch"]
    code, out, err = _run_script(args, timeout=600)
    return _format_output(code, out, err)


@mcp.tool()
def run_reconciliation(year: int, month: int) -> str:
    """
    Run Colppy ↔ HubSpot reconciliation (4-group report).
    Requires colppy_export.db and facturacion_hubspot.db to be refreshed first.
    Returns summary + group tables (MATCH, date mismatches, wrong stage, HubSpot-only).
    """
    if err := _validate_year_month(year, month):
        return f"Validation error: {err}"
    args = [
        "tools/scripts/colppy/reconcile_colppy_hubspot_db_only.py",
        "--year",
        str(year),
        "--month",
        str(month),
    ]
    code, out, err = _run_script(args, timeout=60)
    return _format_output(code, out, err)


@mcp.tool()
def run_full_refresh(year: int, month: int, skip_colppy: bool = False) -> str:
    """
    Orchestrate full refresh for a month: Colppy DB → HubSpot deals → deal associations → reconciliation.
    Use skip_colppy=True when Colppy MySQL is unreachable (VPN off); reconciliation will use stale Colppy data.
    """
    if err := _validate_year_month(year, month):
        return f"Validation error: {err}"
    results = []
    if not skip_colppy:
        code, out, err = _run_script(
            ["tools/scripts/colppy/export_colppy_to_sqlite.py"], timeout=300
        )
        results.append(f"=== Colppy refresh ===\n{_format_output(code, out, err)}")
        if code != 0:
            return "\n\n".join(results) + "\n\nColppy refresh failed; stopping."
    args = [
        "tools/scripts/hubspot/build_facturacion_hubspot_mapping.py",
        "--refresh-deals-only",
        "--year",
        str(year),
        "--month",
        str(month),
        "--fetch-wrong-stage",
    ]
    code, out, err = _run_script(args, timeout=300)
    results.append(f"=== HubSpot refresh ===\n{_format_output(code, out, err)}")
    if code != 0:
        return "\n\n".join(results) + "\n\nHubSpot refresh failed; stopping."
    code, out, err = _run_script(
        ["tools/scripts/hubspot/populate_deal_associations.py", "--batch"],
        timeout=600,
    )
    results.append(f"=== Deal associations ===\n{_format_output(code, out, err)}")
    if code != 0:
        return "\n\n".join(results) + "\n\nDeal associations failed; stopping."
    code, out, err = _run_script(
        [
            "tools/scripts/colppy/reconcile_colppy_hubspot_db_only.py",
            "--year",
            str(year),
            "--month",
            str(month),
        ],
        timeout=60,
    )
    results.append(f"=== Reconciliation ===\n{_format_output(code, out, err)}")
    return "\n\n".join(results)


if __name__ == "__main__":
    mcp.run(transport="stdio")
