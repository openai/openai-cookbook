#!/usr/bin/env python3
"""
HubSpot Analysis MCP Server
===========================
Exposes funnel, scoring, and visualization tools via Model Context Protocol
for use in Cursor, Claude Desktop, etc.

Tools:
- run_smb_mql_funnel: SMB MQL funnel (MQL PYME → Deal Created → Won)
- run_accountant_mql_funnel: Accountant MQL funnel
- run_smb_accountant_involved_funnel: SMB funnel WITH vs WITHOUT accountant
- run_high_score_analysis: Score 40+ contactability and conversion
- run_mtd_scoring: Month-to-date scoring comparison (SQL/PQL by score range)
- run_visualization_report: HTML report from high_score CSV output

Usage:
    python mcp_hubspot_analysis_server.py
    # Or: uv run mcp_hubspot_analysis_server.py

Cursor/Claude Desktop config (~/.cursor/mcp.json or claude_desktop_config.json):
    "hubspot-analysis": {
      "command": "python",
      "args": ["/path/to/openai-cookbook/tools/scripts/hubspot/mcp_hubspot_analysis_server.py"],
      "cwd": "/path/to/openai-cookbook"
    }
"""
import subprocess
import sys
from pathlib import Path
from calendar import monthrange

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

# Load .env for HUBSPOT_API_KEY
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv(REPO_ROOT / "tools" / ".env")
except ImportError:
    pass


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


def _format_output(exit_code: int, stdout: str, stderr: str) -> str:
    """Format subprocess output for MCP tool response."""
    parts = []
    if stdout:
        parts.append(stdout.strip())
    if stderr:
        parts.append(f"stderr:\n{stderr.strip()}")
    parts.append(f"\nExit code: {exit_code}")
    return "\n\n".join(parts)


def _months_to_args(months: str) -> list[str]:
    """Convert space-separated months (e.g. '2025-12 2026-01') to --months arg list."""
    return [m.strip() for m in months.split() if m.strip()]


# FastMCP must be imported after path setup
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hubspot-analysis")


@mcp.tool()
def run_smb_mql_funnel(months: str) -> str:
    """
    Run SMB MQL funnel analysis (MQL PYME → Deal Created → Won).
    months: Space-separated months in YYYY-MM format (e.g. "2025-12 2026-01 2026-02").
    Output: Markdown tables + CSV in tools/outputs/.
    """
    month_list = _months_to_args(months)
    if not month_list:
        return "Error: months must be non-empty (e.g. '2025-12 2026-01')"
    args = ["tools/scripts/hubspot/analyze_smb_mql_funnel.py", "--months"] + month_list
    code, out, err = _run_script(args, timeout=300)
    return _format_output(code, out, err)


@mcp.tool()
def run_accountant_mql_funnel(months: str) -> str:
    """
    Run Accountant MQL funnel analysis (MQL Contador → Deal Created → Won).
    months: Space-separated months in YYYY-MM format (e.g. "2025-12 2026-01").
    Output: Markdown tables + CSV in tools/outputs/.
    """
    month_list = _months_to_args(months)
    if not month_list:
        return "Error: months must be non-empty (e.g. '2025-12 2026-01')"
    args = ["tools/scripts/hubspot/analyze_accountant_mql_funnel.py", "--months"] + month_list
    code, out, err = _run_script(args, timeout=300)
    return _format_output(code, out, err)


@mcp.tool()
def run_smb_accountant_involved_funnel(
    months: str,
    minimal: bool = False,
    dual_criteria: bool = False,
) -> str:
    """
    Run SMB funnel WITH vs WITHOUT accountant involvement.
    months: Space-separated months in YYYY-MM format (e.g. "2025-12 2026-01").
    minimal: Skip contact filter and ICP coverage for faster run.
    dual_criteria: Also check association type 8 per deal (slower).
    Output: Markdown tables + CSV in tools/outputs/.
    """
    month_list = _months_to_args(months)
    if not month_list:
        return "Error: months must be non-empty (e.g. '2025-12 2026-01')"
    args = ["tools/scripts/hubspot/analyze_smb_accountant_involved_funnel.py", "--months"] + month_list
    if minimal:
        args.append("--minimal")
    if dual_criteria:
        args.append("--dual-criteria")
    code, out, err = _run_script(args, timeout=600)
    return _format_output(code, out, err)


@mcp.tool()
def run_high_score_analysis(
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    current_mtd: bool = False,
) -> str:
    """
    Run high-score (40+) sales handling analysis: contactability, owner performance, SQL/PQL conversion.
    Provide one of: month (YYYY-MM), start_date+end_date (YYYY-MM-DD), or current_mtd=True.
    Output: Markdown tables + CSV in tools/outputs/.
    """
    args = ["tools/scripts/hubspot/high_score_sales_handling_analysis.py"]
    if current_mtd:
        args.append("--current-mtd")
    elif month:
        args.extend(["--month", month])
    elif start_date and end_date:
        args.extend(["--start-date", start_date, "--end-date", end_date])
    else:
        args.append("--current-mtd")
    code, out, err = _run_script(args, timeout=120)
    return _format_output(code, out, err)


@mcp.tool()
def run_mtd_scoring(month1: str, month2: str) -> str:
    """
    Run month-to-date scoring comparison: SQL/PQL conversion by score range (40+, 30-39, etc.).
    month1: First period in YYYY-MM (e.g. "2026-01").
    month2: Second period in YYYY-MM (e.g. "2026-02").
    Output: Markdown tables + CSV in tools/outputs/.
    """
    args = [
        "tools/scripts/hubspot/mtd_scoring_full_pagination.py",
        "--month1", month1,
        "--month2", month2,
    ]
    code, out, err = _run_script(args, timeout=300)
    return _format_output(code, out, err)


@mcp.tool()
def run_visualization_report(month: str) -> str:
    """
    Generate HTML visualization report from high_score analysis output.
    month: Month in YYYY-MM (e.g. "2026-02"). Expects high_score_contacts_* and high_score_owner_performance_* CSVs in tools/outputs/.
    Run run_high_score_analysis for that month first if files are missing.
    Output: tools/outputs/high_score_visualization_report_YYYY_MM.html
    """
    try:
        year, month_num = month.split("-")
        year_int = int(year)
        month_int = int(month_num)
        last_day = monthrange(year_int, month_int)[1]
        start_str = f"{year}-{month_num}-01"
        end_str = f"{year}-{month_num}-{last_day:02d}"
        period_suffix = start_str.replace("-", "_") + "_" + end_str.replace("-", "_")
    except (ValueError, IndexError):
        return f"Error: month must be YYYY-MM (e.g. '2026-02'), got '{month}'"

    output_dir = REPO_ROOT / "tools" / "outputs"
    contacts_file = output_dir / f"high_score_contacts_{period_suffix}.csv"
    owners_file = output_dir / f"high_score_owner_performance_{period_suffix}.csv"

    if not contacts_file.exists():
        return f"Error: {contacts_file} not found. Run run_high_score_analysis(month='{month}') first."
    if not owners_file.exists():
        return f"Error: {owners_file} not found. Run run_high_score_analysis(month='{month}') first."

    out_html = output_dir / f"high_score_visualization_report_{year}_{month_num}.html"
    args = [
        "tools/scripts/hubspot/generate_visualization_report.py",
        "--contacts-file", str(contacts_file),
        "--owners-file", str(owners_file),
        "--output", str(out_html),
    ]
    code, out, err = _run_script(args, timeout=60)
    result = _format_output(code, out, err)
    if code == 0:
        result = f"Report saved to: {out_html}\n\n" + result
    return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
