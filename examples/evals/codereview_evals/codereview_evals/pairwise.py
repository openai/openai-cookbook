from __future__ import annotations

import csv
import json
from html import escape
from pathlib import Path
from typing import Callable

from .benchmark import (
    _build_openai_client,
    _emit_progress,
    _run_json_schema_completion,
    build_reviewer_input,
)
from .github_cache import DEFAULT_CACHE_ROOT, load_cached_pull_requests
from .reporting import default_run_id
from .types import HarnessConfig, JSONDict, RunArtifacts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAIRWISE_HARNESS_DIR = PROJECT_ROOT / "2_pairwise_harness"


def load_pairwise_harness_bundle(
    harness_dir: Path = DEFAULT_PAIRWISE_HARNESS_DIR,
) -> tuple[HarnessConfig, str, str, str, str, str, JSONDict, JSONDict]:
    config_data = json.loads((harness_dir / "eval_config.json").read_text(encoding="utf-8"))
    config = HarnessConfig(
        model=str(config_data["model"]),
        grader_model=str(config_data["grader_model"]),
    )
    experiment_agents = (harness_dir / "AGENTS.md").read_text(encoding="utf-8").strip()
    baseline_agents = (harness_dir / "baseline_AGENTS.md").read_text(encoding="utf-8").strip()
    candidate_agents = (harness_dir / "candidate_AGENTS.md").read_text(encoding="utf-8").strip()
    reviewer_prompt = (harness_dir / "reviewer_system.txt").read_text(encoding="utf-8").strip()
    judge_prompt = (harness_dir / "pairwise_judge_system.txt").read_text(encoding="utf-8").strip()
    review_schema = json.loads((harness_dir / "review_output_schema.json").read_text(encoding="utf-8"))
    judge_schema = json.loads((harness_dir / "pairwise_output_schema.json").read_text(encoding="utf-8"))
    return (
        config,
        experiment_agents,
        baseline_agents,
        candidate_agents,
        reviewer_prompt,
        judge_prompt,
        review_schema,
        judge_schema,
    )


def run_pairwise(
    *,
    cache_key: str,
    max_prs: int | None,
    run_name: str = "",
    cache_root: Path = DEFAULT_CACHE_ROOT,
    harness_dir: Path = DEFAULT_PAIRWISE_HARNESS_DIR,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[RunArtifacts, JSONDict]:
    (
        config,
        experiment_agents,
        baseline_agents,
        candidate_agents,
        reviewer_prompt,
        judge_prompt,
        review_schema,
        judge_schema,
    ) = load_pairwise_harness_bundle(harness_dir)
    snapshots = load_cached_pull_requests(cache_root, cache_key=cache_key)
    if max_prs and max_prs > 0:
        snapshots = snapshots[:max_prs]

    client = _build_openai_client()
    results: list[JSONDict] = []
    total_snapshots = len(snapshots)
    for index, snapshot in enumerate(snapshots, start=1):
        pr_number = snapshot.get("number")
        pr_title = str(snapshot.get("title", "")).strip()
        _emit_progress(
            progress_callback,
            f"[{index}/{total_snapshots}] Pairwise compare PR #{pr_number} {pr_title}".rstrip(),
        )
        try:
            baseline_review = _run_json_schema_completion(
                client=client,
                model=config.model,
                system_prompt=reviewer_prompt,
                user_content=build_reviewer_input(snapshot, baseline_agents),
                schema_name="baseline_review_output",
                schema=review_schema,
            )
            candidate_review = _run_json_schema_completion(
                client=client,
                model=config.model,
                system_prompt=reviewer_prompt,
                user_content=build_reviewer_input(snapshot, candidate_agents),
                schema_name="candidate_review_output",
                schema=review_schema,
            )
            judgment = _run_json_schema_completion(
                client=client,
                model=config.grader_model,
                system_prompt=judge_prompt,
                user_content=build_pairwise_judge_input(
                    snapshot=snapshot,
                    experiment_agents=experiment_agents,
                    baseline_agents=baseline_agents,
                    candidate_agents=candidate_agents,
                    baseline_review=baseline_review,
                    candidate_review=candidate_review,
                ),
                schema_name="pairwise_comparison",
                schema=judge_schema,
            )
            results.append(
                build_pairwise_result_row(
                    snapshot=snapshot,
                    baseline_review=baseline_review,
                    candidate_review=candidate_review,
                    judgment=judgment,
                    config=config,
                )
            )
            _emit_progress(
                progress_callback,
                f"[{index}/{total_snapshots}] Completed PR #{pr_number} ({len(results)} processed)",
            )
        except Exception as exc:  # pragma: no cover - exercised through CLI smoke paths
            results.append(build_pairwise_failure_row(snapshot=snapshot, error_message=str(exc), config=config))
            _emit_progress(
                progress_callback,
                f"[{index}/{total_snapshots}] Failed PR #{pr_number} ({len(results)} processed): {exc}",
            )

    run_dir = harness_dir / "results" / default_run_id(run_name)
    return write_pairwise_results(run_dir=run_dir, results=results)


def render_pairwise_report(*, run_dir: Path) -> Path:
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    report_path = run_dir / "report.html"
    report_path.write_text(
        render_pairwise_report_html(results=results, summary=summary),
        encoding="utf-8",
    )
    return report_path


def build_pairwise_judge_input(
    *,
    snapshot: JSONDict,
    experiment_agents: str,
    baseline_agents: str,
    candidate_agents: str,
    baseline_review: JSONDict,
    candidate_review: JSONDict,
) -> str:
    baseline_review_json = json.dumps(baseline_review, indent=2, ensure_ascii=False)
    candidate_review_json = json.dumps(candidate_review, indent=2, ensure_ascii=False)
    return "\n\n".join(
        [
            f"Pull request: #{snapshot.get('number')} {snapshot.get('title', '')}",
            f"URL: {snapshot.get('url', '')}",
            "Experiment goal:\n" + (experiment_agents or "(empty)"),
            "Baseline AGENTS.md:\n" + (baseline_agents or "(empty)"),
            "Candidate AGENTS.md:\n" + (candidate_agents or "(empty)"),
            "Baseline review JSON:\n" + baseline_review_json,
            "Candidate review JSON:\n" + candidate_review_json,
        ]
    )


def build_pairwise_result_row(
    *,
    snapshot: JSONDict,
    baseline_review: JSONDict,
    candidate_review: JSONDict,
    judgment: JSONDict,
    config: HarnessConfig,
) -> JSONDict:
    baseline_comments = list(baseline_review.get("comments") or [])
    candidate_comments = list(candidate_review.get("comments") or [])
    return {
        "status": "ok",
        "pr_number": snapshot.get("number"),
        "pr_title": snapshot.get("title", ""),
        "pr_url": snapshot.get("url", ""),
        "merged": bool(snapshot.get("merged")),
        "reviewer_model": config.model,
        "grader_model": config.grader_model,
        "baseline_summary": str(baseline_review.get("summary") or "").strip(),
        "baseline_comments": baseline_comments,
        "baseline_comment_count": len(baseline_comments),
        "candidate_summary": str(candidate_review.get("summary") or "").strip(),
        "candidate_comments": candidate_comments,
        "candidate_comment_count": len(candidate_comments),
        "winner": str(judgment.get("winner") or "").strip(),
        "judge_confidence": float(judgment.get("confidence", 0) or 0),
        "judge_reason": str(judgment.get("reason") or "").strip(),
        "error_message": "",
    }


def build_pairwise_failure_row(
    *,
    snapshot: JSONDict,
    error_message: str,
    config: HarnessConfig,
) -> JSONDict:
    return {
        "status": "failed",
        "pr_number": snapshot.get("number"),
        "pr_title": snapshot.get("title", ""),
        "pr_url": snapshot.get("url", ""),
        "merged": bool(snapshot.get("merged")),
        "reviewer_model": config.model,
        "grader_model": config.grader_model,
        "baseline_summary": "",
        "baseline_comments": [],
        "baseline_comment_count": 0,
        "candidate_summary": "",
        "candidate_comments": [],
        "candidate_comment_count": 0,
        "winner": "",
        "judge_confidence": 0.0,
        "judge_reason": "",
        "error_message": error_message,
    }


def summarize_pairwise_results(results: list[JSONDict]) -> JSONDict:
    successful = [row for row in results if row.get("status") == "ok"]
    baseline_wins = [row for row in successful if row.get("winner") == "baseline"]
    candidate_wins = [row for row in successful if row.get("winner") == "candidate"]
    ties = [row for row in successful if row.get("winner") == "tie"]
    merged_rows = [row for row in successful if bool(row.get("merged"))]
    closed_rows = [row for row in successful if not bool(row.get("merged"))]
    return {
        "total_examples": len(results),
        "successful_examples": len(successful),
        "failed_examples": len(results) - len(successful),
        "baseline_wins": len(baseline_wins),
        "candidate_wins": len(candidate_wins),
        "ties": len(ties),
        "baseline_win_rate": _rate(len(baseline_wins), len(successful)),
        "candidate_win_rate": _rate(len(candidate_wins), len(successful)),
        "tie_rate": _rate(len(ties), len(successful)),
        "merged_examples": len(merged_rows),
        "closed_unmerged_examples": len(closed_rows),
        "candidate_win_rate_merged": _segment_rate(merged_rows, "candidate"),
        "candidate_win_rate_closed_unmerged": _segment_rate(closed_rows, "candidate"),
    }


def write_pairwise_results(*, run_dir: Path, results: list[JSONDict]) -> tuple[RunArtifacts, JSONDict]:
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_pairwise_results(results)

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
        render_pairwise_report_html(results=results, summary=summary),
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


def render_pairwise_report_html(*, results: list[JSONDict], summary: JSONDict) -> str:
    cards = "".join(
        _render_card(label, summary.get(key))
        for label, key in [
            ("Total examples", "total_examples"),
            ("Candidate wins", "candidate_wins"),
            ("Baseline wins", "baseline_wins"),
            ("Ties", "ties"),
            ("Candidate win rate", "candidate_win_rate"),
            ("Baseline win rate", "baseline_win_rate"),
            ("Merged candidate win", "candidate_win_rate_merged"),
            ("Closed candidate win", "candidate_win_rate_closed_unmerged"),
            ("Failed", "failed_examples"),
        ]
    )
    rows_html = "".join(_render_pairwise_row(result) for result in results)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Level 2 Pairwise Harness Report</title>
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
  <h1>Level 2 Pairwise Harness Report</h1>
  <p class="meta">Static report generated from saved pairwise comparison artifacts.</p>
  <div class="cards">{cards}</div>
  <table>
    <thead>
      <tr>
        <th style="width: 10%">PR</th>
        <th style="width: 8%">Status</th>
        <th style="width: 7%">Merged</th>
        <th style="width: 20%">Baseline Review</th>
        <th style="width: 20%">Candidate Review</th>
        <th style="width: 10%">Winner</th>
        <th style="width: 10%">Confidence</th>
        <th style="width: 15%">Judge Reason</th>
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


def _render_card(label: str, value: object) -> str:
    if isinstance(value, float):
        rendered = f"{value:.2f}"
    else:
        rendered = str(value)
    return (
        "<div class='card'>"
        f"<div class='label'>{escape(label)}</div>"
        f"<div class='value'>{escape(rendered)}</div>"
        "</div>"
    )


def _render_pairwise_row(result: JSONDict) -> str:
    pr_label = f"#{result.get('pr_number', '')}"
    pr_link = str(result.get("pr_url", ""))
    merged = "merged" if result.get("merged") else "closed"
    status = str(result.get("status", ""))
    status_class = "status-ok" if status == "ok" else "status-failed"
    winner = str(result.get("winner", "")) or "error"
    confidence = result.get("judge_confidence", "")
    baseline_summary = result.get("baseline_summary", "") or result.get("error_message", "")
    candidate_summary = result.get("candidate_summary", "")
    return (
        "<tr>"
        f"<td><a href='{escape(pr_link)}'>{escape(pr_label)}</a><br>{escape(str(result.get('pr_title', '')))}</td>"
        f"<td><span class='{status_class}'>{escape(status or 'unknown')}</span></td>"
        f"<td>{escape(merged)}</td>"
        f"<td><pre>{escape(str(baseline_summary))}</pre>{_render_comments_list(result.get('baseline_comments'))}</td>"
        f"<td><pre>{escape(str(candidate_summary))}</pre>{_render_comments_list(result.get('candidate_comments'))}</td>"
        f"<td>{escape(winner)}</td>"
        f"<td>{escape(f'{float(confidence):.2f}' if confidence != '' else '')}</td>"
        f"<td><pre>{escape(str(result.get('judge_reason', '')))}</pre></td>"
        "</tr>"
    )


def _render_comments_list(comments: object) -> str:
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


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return count / total


def _segment_rate(rows: list[JSONDict], winner: str) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if row.get("winner") == winner) / len(rows)
