#!/usr/bin/env python3
"""
Refresh Building Blocks Budget Dashboard
========================================
Fetches colppy_budget and asp_forecast_2026 from Google Sheets (via registry),
parses Budget vs REAL for Jan-2026, and regenerates docs/budget_dashboard.html.

Usage:
    python tools/scripts/refresh_budget_dashboard.py
    python tools/scripts/refresh_budget_dashboard.py --output docs/budget_dashboard.html

Requires: tools/docs/GOOGLE_SHEETS_REGISTRY.json
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "tools" / "docs" / "GOOGLE_SHEETS_REGISTRY.json"


def parse_num(s):
    """Parse number from CSV (handles 1,234,567 US and 1.234.567 Argentina)."""
    if not s or not str(s).strip():
        return None
    s = str(s).strip().replace("$", "").replace(" ", "").replace('"', "")
    if not s:
        return None
    orig = s
    if "," in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            s = parts[0] + "." + parts[1]
        else:
            s = s.replace(",", "")
    if "." in s and s.count(".") > 1:
        s = s.replace(".", "", s.count(".") - 1)
    try:
        return float(s)
    except ValueError:
        return None


def fetch_tab(file_id: str, gid: str) -> str:
    """Fetch CSV from Google Sheets via curl."""
    url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv&gid={gid}"
    r = subprocess.run(
        ["curl", "-sL", url],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if r.returncode != 0:
        raise RuntimeError(f"curl failed: {r.stderr}")
    return r.stdout


def parse_budget_csv(csv_text: str, target_month: str = "Jan-2026"):
    """Parse Budget and REAL sections, return {item: (budget, real)}."""
    rows = list(csv.reader(csv_text.splitlines()))
    if len(rows) < 3:
        return {}
    h = rows[1]
    col_item = next((i for i, c in enumerate(h) if c == "Item"), 4)
    col_month = next((i for i, c in enumerate(h) if c == target_month), None)
    if col_month is None:
        return {}
    budget = {}
    real = {}
    in_real = False
    skip = {"Sub-total", "Forecast", "Increase", "Price", "Monthly", "Total", "Referencias"}
    for r in rows[2:]:
        if len(r) <= col_item:
            continue
        item = (r[col_item] or "").strip()
        if "REAL" in item:
            in_real = True
            continue
        if not item or any(x in item for x in skip):
            continue
        val = parse_num(r[col_month]) if len(r) > col_month else None
        if val is None:
            continue
        norm = item.replace("Admnisitración", "Administración")
        if in_real:
            real[norm] = val
        else:
            budget[norm] = val
    out = {}
    for k in budget:
        if k in real:
            out[k] = (budget[k], real[k])
    return out


def fmt_ars(n: float) -> str:
    """Format as ARS with period thousands, comma decimals."""
    if n is None or (isinstance(n, float) and (n != n)):
        return "—"
    s = f"{abs(n):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if n < 0 else "") + s.rstrip("0").rstrip(",")


def fmt_pct(pct: float) -> str:
    """Format percentage Argentina style."""
    if pct is None or (isinstance(pct, float) and (pct != pct)):
        return "—"
    s = f"{pct:+.1f}%".replace(".", ",")
    return s


def build_html(mrr_rows: list, asp_rows: list, summary: dict, output_path: Path):
    """Generate budget_dashboard.html."""
    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Colppy - Building Blocks Budget vs Actual</title>
    <style>
        :root {{
            --bg: #0f172a; --card: #1e293b; --accent: #3b82f6; --accent-dim: #1e40af;
            --text: #f1f5f9; --text-muted: #94a3b8; --success: #22c55e; --danger: #ef4444;
            --border: #334155;
        }}
        * {{ box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; min-height: 100vh; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ font-size: 1.5rem; font-weight: 600; margin-bottom: 8px; }}
        .subtitle {{ color: var(--text-muted); font-size: 0.9rem; margin-bottom: 24px; }}
        .detail-generated {{ font-size: 0.8rem; margin: -8px 0 16px 0; color: var(--text-muted); }}
        a {{ color: var(--accent); text-decoration: none; }} a:hover {{ text-decoration: underline; }}
        .summary-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }}
        .summary-card {{ background: var(--card); border-radius: 12px; padding: 16px 20px; border: 1px solid var(--border); }}
        .summary-card h3 {{ font-size: 0.85rem; font-weight: 500; margin: 0 0 8px 0; color: var(--text-muted); }}
        .summary-card .value {{ font-size: 1.25rem; font-weight: 700; }} .summary-card .value.positive {{ color: var(--success); }} .summary-card .value.negative {{ color: var(--danger); }}
        .section {{ background: var(--card); border-radius: 12px; padding: 20px; margin-bottom: 24px; border: 1px solid var(--border); }}
        .section h2 {{ font-size: 1.1rem; font-weight: 600; margin: 0 0 16px 0; }}
        .section p.detail {{ font-size: 0.85rem; color: var(--text-muted); margin: 0 0 12px 0; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
        th, td {{ padding: 10px 12px; text-align: right; border-bottom: 1px solid var(--border); }}
        th {{ font-weight: 600; color: var(--text-muted); text-align: left; }}
        th.num, td.num {{ text-align: right; }} .item-col {{ text-align: left; font-weight: 500; }}
        .positive {{ color: var(--success); }} .negative {{ color: var(--danger); }}
        table.sortable th {{ cursor: pointer; }} table.sortable th:hover {{ color: var(--accent); }}
        .nav-links {{ margin-bottom: 24px; display: flex; gap: 16px; flex-wrap: wrap; }}
        .nav-links a {{ padding: 8px 14px; background: var(--card); border-radius: 8px; border: 1px solid var(--border); font-size: 0.9rem; }}
    </style>
</head>
<body>
    <div class="container">
        <nav class="nav-links">
            <a href="index.html">← Dashboards</a>
            <a href="mrr_dashboard.html">MRR Dashboard</a>
        </nav>

        <h1>Building Blocks — Budget vs Actual</h1>
        <p class="subtitle">Deviation review: MRR and Average Ticket by product line · January 2026</p>
        <p class="detail-generated">Data source: Google Sheets (Building Blocks Por Producto Q4'25 HLT, ASP Forecast 2026 & Actual). Generated: {gen_time}</p>

        <div class="summary-cards">
'''
    for card in summary.get("cards", []):
        cls = "positive" if card.get("pct", 0) >= 0 else "negative"
        html += f'''            <div class="summary-card">
                <h3>{card["title"]}</h3>
                <span class="value {cls}">{card["pct_str"]}</span>
                <p class="detail" style="margin:8px 0 0 0;font-size:0.8rem">Budget {card["budget_str"]} → Actual {card["actual_str"]}</p>
            </div>
'''
    html += '''        </div>

        <div class="section">
            <h2>MRR — Budget vs Actual (Jan 2026)</h2>
            <p class="detail">Building Blocks Por Producto - Q4'25 HLT. Values in ARS.</p>
            <table class="sortable">
                <thead>
                    <tr>
                        <th>Item</th>
                        <th class="num">Budget (ARS)</th>
                        <th class="num">Actual (ARS)</th>
                        <th class="num">Deviation</th>
                        <th class="num">% Var</th>
                    </tr>
                </thead>
                <tbody>
'''
    for row in mrr_rows:
        cls = "positive" if row["dev"] >= 0 else "negative"
        html += f'''                    <tr>
                        <td class="item-col">{row["item"]}</td>
                        <td class="num">{row["budget_str"]}</td>
                        <td class="num">{row["actual_str"]}</td>
                        <td class="num {cls}">{row["dev_str"]}</td>
                        <td class="num {cls}">{row["pct_str"]}</td>
                    </tr>
'''
    html += '''                </tbody>
            </table>
        </div>

        <div class="section">
            <h2>Average Ticket (ASP) — Budget vs Actual (Jan 2026)</h2>
            <p class="detail">ASP Forecast 2026 & Actual. Values in ARS.</p>
            <table class="sortable">
                <thead>
                    <tr>
                        <th>Item</th>
                        <th class="num">Budget (ARS)</th>
                        <th class="num">Actual (ARS)</th>
                        <th class="num">Deviation</th>
                        <th class="num">% Var</th>
                    </tr>
                </thead>
                <tbody>
'''
    for row in asp_rows:
        cls = "positive" if row["dev"] >= 0 else "negative"
        html += f'''                    <tr>
                        <td class="item-col">{row["item"]}</td>
                        <td class="num">{row["budget_str"]}</td>
                        <td class="num">{row["actual_str"]}</td>
                        <td class="num {cls}">{row["dev_str"]}</td>
                        <td class="num {cls}">{row["pct_str"]}</td>
                    </tr>
'''
    html += '''                </tbody>
            </table>
        </div>

        <div class="section">
            <h2>Key Insights</h2>
            <ul style="color: var(--text-muted); font-size: 0.9rem; line-height: 1.6; margin: 0; padding-left: 20px;">
'''
    for li in summary.get("insights", []):
        html += f"                <li>{li}</li>\n"
    html += """            </ul>
        </div>
    </div>

    <script>
    document.querySelectorAll("table.sortable").forEach(function(table) {
        var headers = table.querySelectorAll("th");
        headers.forEach(function(th, idx) {
            th.addEventListener("click", function() {
                var tbody = table.querySelector("tbody");
                var rows = Array.from(tbody.querySelectorAll("tr"));
                var asc = th.getAttribute("data-sort") !== "asc";
                th.setAttribute("data-sort", asc ? "asc" : "desc");
                rows.sort(function(a, b) {
                    var va = a.cells[idx] ? a.cells[idx].textContent.trim() : "";
                    var vb = b.cells[idx] ? b.cells[idx].textContent.trim() : "";
                    var isNum = /^[+-]?[\\d.,\\s]+%?$/.test(va);
                    if (isNum) {
                        var parseVal = function(s) {
                            var n = parseFloat(s.replace(/[.\\s]/g, "").replace(",", ".").replace(/[^0-9.-]/g, "")) || 0;
                            return s.includes("-") && s.indexOf("-") < 3 ? -Math.abs(n) : n;
                        };
                        var na = parseVal(va), nb = parseVal(vb);
                        return asc ? na - nb : nb - na;
                    }
                    return asc ? (va < vb ? -1 : va > vb ? 1 : 0) : (vb < va ? -1 : vb > va ? 1 : 0);
                });
                rows.forEach(function(r) { tbody.appendChild(r); });
            });
        });
    });
    </script>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Refresh Building Blocks budget dashboard")
    parser.add_argument("--output", default="docs/budget_dashboard.html", help="Output HTML path")
    parser.add_argument("--registry", default=str(REGISTRY), help="Path to GOOGLE_SHEETS_REGISTRY.json")
    args = parser.parse_args()

    reg = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    tabs = {t["id"]: t for t in reg["tabs"]}
    colppy = tabs.get("colppy_budget")
    asp = tabs.get("asp_forecast_2026")
    if not colppy or not asp:
        print("Registry missing colppy_budget or asp_forecast_2026", file=sys.stderr)
        sys.exit(1)

    print("Fetching colppy_budget...")
    csv_budget = fetch_tab(colppy["file_id"], colppy["gid"])
    print("Fetching asp_forecast_2026...")
    csv_asp = fetch_tab(asp["file_id"], asp["gid"])

    mrr_data = parse_budget_csv(csv_budget)
    asp_data = parse_budget_csv(csv_asp)

    mrr_rows = []
    for item in sorted(mrr_data.keys()):
        b, r = mrr_data[item]
        dev = r - b
        pct = (dev / b * 100) if b else 0
        mrr_rows.append({
            "item": item,
            "budget": b,
            "actual": r,
            "dev": dev,
            "pct": pct,
            "budget_str": fmt_ars(b),
            "actual_str": fmt_ars(r),
            "dev_str": ("+" if dev >= 0 else "") + fmt_ars(dev),
            "pct_str": fmt_pct(pct),
        })

    asp_rows = []
    for item in sorted(asp_data.keys()):
        b, r = asp_data[item]
        dev = r - b
        pct = (dev / b * 100) if b else 0
        asp_rows.append({
            "item": item,
            "budget": b,
            "actual": r,
            "dev": dev,
            "pct": pct,
            "budget_str": fmt_ars(b),
            "actual_str": fmt_ars(r),
            "dev_str": ("+" if dev >= 0 else "") + fmt_ars(dev),
            "pct_str": fmt_pct(pct),
        })

    new_product = sum(r["actual"] for r in mrr_rows if "New Product" in r["item"])
    new_product_b = sum(r["budget"] for r in mrr_rows if "New Product" in r["item"])
    upsell = sum(r["actual"] for r in mrr_rows if "Upsell" in r["item"])
    upsell_b = sum(r["budget"] for r in mrr_rows if "Upsell" in r["item"])
    cross = next((r for r in mrr_rows if "Cross sell" in r["item"]), None)
    eop = next((r for r in mrr_rows if r["item"] == "EoP"), None)
    avg_new = next((r for r in asp_rows if "Average New" in r["item"] or "New Product" in r["item"] and "Average" in str(asp_rows)), None)
    avg_upsell = next((r for r in asp_rows if "Average Upsell" in r["item"] or "Upselling" in r["item"]), None)

    def card(title, b, a):
        pct = ((a - b) / b * 100) if b else 0
        return {"title": title, "budget_str": fmt_ars(b), "actual_str": fmt_ars(a), "pct": pct, "pct_str": fmt_pct(pct)}

    cards = []
    if new_product_b and new_product is not None:
        cards.append(card("New Product MRR", new_product_b, new_product))
    if upsell_b and upsell is not None:
        cards.append(card("Upsell MRR", upsell_b, upsell))
    if cross:
        cards.append(card("Cross Sell MRR", cross["budget"], cross["actual"]))
    if eop:
        cards.append(card("EoP MRR", eop["budget"], eop["actual"]))
    if avg_new:
        cards.append(card("Avg Ticket New Product", avg_new["budget"], avg_new["actual"]))
    if avg_upsell:
        cards.append(card("Avg Ticket Upselling", avg_upsell["budget"], avg_upsell["actual"]))

    insights = []
    for r in mrr_rows[:8]:
        if abs(r["pct"]) > 20:
            insights.append(f"<strong>{r['item']}</strong>: {r['pct_str']} vs budget ({r['dev_str']} ARS)")
    if asp_rows:
        for r in asp_rows[-2:]:
            insights.append(f"<strong>{r['item']}</strong>: {r['pct_str']} vs budget")
    if not insights:
        insights = ["Data refreshed. Review tables for detailed deviations."]

    summary = {"cards": cards, "insights": insights}
    out_path = REPO_ROOT / args.output
    build_html(mrr_rows, asp_rows, summary, out_path)
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
