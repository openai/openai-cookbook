from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from .types import JSONDict, RunArtifacts


def default_run_id(run_name: str = "") -> str:
    if run_name:
        return run_name
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def write_results(
    *,
    run_dir: Path,
    results: list[JSONDict],
    report_title: str,
) -> tuple[RunArtifacts, JSONDict]:
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_results(results)

    results_json = run_dir / "results.json"
    results_csv = run_dir / "results.csv"
    summary_json = run_dir / "summary.json"
    report_html = run_dir / "report.html"

    results_json.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    summary_json.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_csv(results_csv, results)
    report_html.write_text(
        render_report_html(results=results, summary=summary, title=report_title),
        encoding="utf-8",
    )

    artifacts = RunArtifacts(
        run_dir=run_dir,
        results_json=results_json,
        results_csv=results_csv,
        summary_json=summary_json,
        report_html=report_html,
    )
    return artifacts, summary


def render_report_for_run(*, run_dir: Path, report_title: str) -> Path:
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    report_path = run_dir / "report.html"
    report_path.write_text(
        render_report_html(results=results, summary=summary, title=report_title),
        encoding="utf-8",
    )
    return report_path


def summarize_results(results: list[JSONDict]) -> JSONDict:
    successful = [row for row in results if row.get("status") == "ok"]
    summary: JSONDict = {
        "total_examples": len(results),
        "successful_examples": len(successful),
        "failed_examples": len(results) - len(successful),
        "pass_rate": _mean(successful, "grader_overall_pass"),
        "correctness_rate": _mean(successful, "grader_correctness"),
        "usefulness_rate": _mean(successful, "grader_usefulness"),
        "low_noise_rate": _mean(successful, "grader_noise"),
    }

    merged_rows = [row for row in successful if bool(row.get("merged"))]
    closed_rows = [row for row in successful if not bool(row.get("merged"))]
    summary["merged_examples"] = len(merged_rows)
    summary["closed_unmerged_examples"] = len(closed_rows)
    summary["merged_pass_rate"] = _mean(merged_rows, "grader_overall_pass")
    summary["closed_unmerged_pass_rate"] = _mean(closed_rows, "grader_overall_pass")
    return summary


def render_report_html(*, results: list[JSONDict], summary: JSONDict, title: str) -> str:
    cards = "".join(
        _render_card(label, summary.get(key))
        for label, key in [
            ("Total examples", "total_examples"),
            ("Pass rate", "pass_rate"),
            ("Correctness", "correctness_rate"),
            ("Usefulness", "usefulness_rate"),
            ("Low-noise", "low_noise_rate"),
            ("Merged pass", "merged_pass_rate"),
            ("Closed pass", "closed_unmerged_pass_rate"),
            ("Failed", "failed_examples"),
        ]
    )

    rows_html = "".join(_render_result_row(result) for result in results)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #1f2937; }}
    h1 {{ margin-bottom: 8px; }}
    p.meta {{ color: #6b7280; margin-top: 0; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 24px 0; }}
    .card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 16px; background: #f9fafb; }}
    .card .label {{ font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.04em; }}
    .card .value {{ font-size: 24px; font-weight: 600; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 10px; vertical-align: top; text-align: left; font-size: 14px; }}
    th {{ background: #f3f4f6; }}
    code, pre {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    pre {{ white-space: pre-wrap; word-break: break-word; margin: 0; }}
    ul {{ margin: 0; padding-left: 18px; }}
    .status-ok {{ color: #166534; font-weight: 600; }}
    .status-failed {{ color: #991b1b; font-weight: 600; }}
  </style>
</head>
<body>
  <h1>{escape(title)}</h1>
  <p class="meta">Static report generated from saved benchmark artifacts.</p>
  <div class="cards">{cards}</div>
  <table>
    <thead>
      <tr>
        <th style="width: 10%">PR</th>
        <th style="width: 8%">Status</th>
        <th style="width: 8%">Merged</th>
        <th style="width: 20%">Reviewer Summary</th>
        <th style="width: 24%">Generated Comments</th>
        <th style="width: 10%">Scores</th>
        <th style="width: 20%">Judge Reason</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</body>
</html>
"""


def _write_csv(path: Path, results: list[JSONDict]) -> None:
    flattened = [_flatten_row(row) for row in results]
    fieldnames: list[str] = []
    for row in flattened:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flattened)


def _flatten_row(row: JSONDict) -> JSONDict:
    flattened: JSONDict = {}
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            flattened[key] = json.dumps(value, ensure_ascii=False)
        else:
            flattened[key] = value
    return flattened


def _render_card(label: str, value: Any) -> str:
    return (
        "<div class='card'>"
        f"<div class='label'>{escape(label)}</div>"
        f"<div class='value'>{escape(_format_metric(value))}</div>"
        "</div>"
    )


def _format_metric(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _render_result_row(result: JSONDict) -> str:
    pr_label = f"#{result.get('pr_number', '')}"
    pr_link = result.get("pr_url", "")
    merged = "merged" if result.get("merged") else "closed"
    comments = result.get("reviewer_comments") or []
    comments_html = _render_comments_list(comments)
    scores_html = "<pre>" + escape(
        "\n".join(
            [
                f"pass={result.get('grader_overall_pass', '')}",
                f"correctness={result.get('grader_correctness', '')}",
                f"usefulness={result.get('grader_usefulness', '')}",
                f"noise={result.get('grader_noise', '')}",
            ]
        )
    ) + "</pre>"
    status = str(result.get("status", ""))
    status_class = "status-ok" if status == "ok" else "status-failed"
    status_text = status or "unknown"
    summary_text = result.get("reviewer_summary", "") or result.get("error_message", "")
    return (
        "<tr>"
        f"<td><a href='{escape(pr_link)}'>{escape(pr_label)}</a><br>{escape(str(result.get('pr_title', '')))}</td>"
        f"<td><span class='{status_class}'>{escape(status_text)}</span></td>"
        f"<td>{escape(merged)}</td>"
        f"<td><pre>{escape(str(summary_text))}</pre></td>"
        f"<td>{comments_html}</td>"
        f"<td>{scores_html}</td>"
        f"<td><pre>{escape(str(result.get('grader_reason', '')))}</pre></td>"
        "</tr>"
    )


def _render_comments_list(comments: Any) -> str:
    if not comments:
        return "<em>No comments</em>"
    items: list[str] = []
    for comment in comments:
        path = comment.get("path", "")
        line = comment.get("line", "")
        severity = comment.get("severity", "")
        claim = comment.get("claim", "")
        items.append(
            "<li>"
            f"<strong>{escape(path)}:{escape(str(line))}</strong> "
            f"[{escape(severity)}] {escape(claim)}"
            "</li>"
        )
    return "<ul>" + "".join(items) + "</ul>"


def _mean(rows: list[JSONDict], key: str) -> float:
    if not rows:
        return 0.0
    total = sum(float(row.get(key, 0) or 0) for row in rows)
    return total / len(rows)
