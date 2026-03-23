from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Callable

from .benchmark import (
    _build_openai_client,
    _emit_progress,
    _run_json_schema_completion,
    build_failure_row,
    build_grader_input,
    build_result_row,
    build_reviewer_input,
)
from .github_cache import DEFAULT_CACHE_ROOT, load_cached_pull_requests
from .pairwise import (
    build_pairwise_failure_row,
    build_pairwise_judge_input,
    build_pairwise_result_row,
    render_pairwise_report_html,
    summarize_pairwise_results,
)
from .reporting import default_run_id, render_report_html, summarize_results
from .types import HarnessConfig, JSONDict, RunArtifacts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPTIMIZER_HARNESS_DIR = PROJECT_ROOT / "3_optimization_harness"


@dataclass(frozen=True)
class OptimizationConfig:
    model: str
    grader_model: str
    optimizer_model: str
    max_steps: int
    score_threshold: float
    pairwise_weight: float
    benchmark_weight: float
    benchmark_guardrail: float


def load_optimizer_harness_bundle(
    harness_dir: Path = DEFAULT_OPTIMIZER_HARNESS_DIR,
) -> tuple[
    OptimizationConfig,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    JSONDict,
    JSONDict,
    JSONDict,
    str,
    JSONDict,
]:
    config_data = json.loads((harness_dir / "eval_config.json").read_text(encoding="utf-8"))
    config = OptimizationConfig(
        model=str(config_data["model"]),
        grader_model=str(config_data["grader_model"]),
        optimizer_model=str(config_data["optimizer_model"]),
        max_steps=int(config_data.get("max_steps", 3)),
        score_threshold=float(config_data.get("score_threshold", 0.7)),
        pairwise_weight=float(config_data.get("pairwise_weight", 0.5)),
        benchmark_weight=float(config_data.get("benchmark_weight", 0.5)),
        benchmark_guardrail=float(config_data.get("benchmark_guardrail", 0.03)),
    )
    experiment_agents = (harness_dir / "AGENTS.md").read_text(encoding="utf-8").strip()
    baseline_agents = (harness_dir / "baseline_AGENTS.md").read_text(encoding="utf-8").strip()
    baseline_system = (harness_dir / "baseline_reviewer_system.txt").read_text(encoding="utf-8").strip()
    candidate_agents = (harness_dir / "candidate_AGENTS.md").read_text(encoding="utf-8").strip()
    candidate_system = (harness_dir / "candidate_reviewer_system.txt").read_text(encoding="utf-8").strip()
    benchmark_grader_system = (
        harness_dir / "benchmark_grader_system.txt"
    ).read_text(encoding="utf-8").strip()
    pairwise_judge_system = (harness_dir / "pairwise_judge_system.txt").read_text(encoding="utf-8").strip()
    optimizer_system = (harness_dir / "optimizer_system.txt").read_text(encoding="utf-8").strip()
    review_schema = json.loads((harness_dir / "review_output_schema.json").read_text(encoding="utf-8"))
    benchmark_schema = json.loads(
        (harness_dir / "benchmark_grader_output_schema.json").read_text(encoding="utf-8")
    )
    pairwise_schema = json.loads((harness_dir / "pairwise_output_schema.json").read_text(encoding="utf-8"))
    optimizer_schema = json.loads((harness_dir / "optimizer_output_schema.json").read_text(encoding="utf-8"))
    return (
        config,
        experiment_agents,
        baseline_agents,
        baseline_system,
        candidate_agents,
        candidate_system,
        benchmark_grader_system,
        pairwise_judge_system,
        review_schema,
        benchmark_schema,
        pairwise_schema,
        optimizer_system,
        optimizer_schema,
    )


def run_optimizer(
    *,
    cache_key: str,
    max_prs: int | None,
    run_name: str = "",
    cache_root: Path = DEFAULT_CACHE_ROOT,
    harness_dir: Path = DEFAULT_OPTIMIZER_HARNESS_DIR,
    progress_callback: Callable[[str], None] | None = None,
    max_steps: int | None = None,
    score_threshold: float | None = None,
) -> tuple[RunArtifacts, JSONDict]:
    (
        config,
        experiment_agents,
        baseline_agents,
        baseline_system,
        seed_candidate_agents,
        seed_candidate_system,
        benchmark_grader_system,
        pairwise_judge_system,
        review_schema,
        benchmark_schema,
        pairwise_schema,
        optimizer_system,
        optimizer_schema,
    ) = load_optimizer_harness_bundle(harness_dir)
    snapshots = load_cached_pull_requests(cache_root, cache_key=cache_key)
    if max_prs and max_prs > 0:
        snapshots = snapshots[:max_prs]

    client = _build_openai_client()
    resolved_max_steps = max_steps if max_steps is not None else config.max_steps
    resolved_score_threshold = score_threshold if score_threshold is not None else config.score_threshold
    run_dir = harness_dir / "results" / default_run_id(run_name)
    steps_dir = run_dir / "steps"
    steps_dir.mkdir(parents=True, exist_ok=True)

    champion_agents = baseline_agents
    champion_system = baseline_system
    champion_label = "baseline_seed"
    champion_benchmark_results, champion_benchmark_summary = _run_pointwise_benchmark(
        snapshots=snapshots,
        client=client,
        reviewer_model=config.model,
        grader_model=config.grader_model,
        reviewer_system=champion_system,
        agents_md=champion_agents,
        grader_system=benchmark_grader_system,
        review_schema=review_schema,
        benchmark_schema=benchmark_schema,
        progress_callback=progress_callback,
        progress_prefix="[baseline benchmark]",
    )
    champion_pass_rate = float(champion_benchmark_summary.get("pass_rate", 0) or 0)

    baseline_dir = run_dir / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    _write_json(baseline_dir / "benchmark_results.json", champion_benchmark_results)
    _write_json(baseline_dir / "benchmark_summary.json", champion_benchmark_summary)
    (baseline_dir / "benchmark_report.html").write_text(
        render_report_html(
            results=champion_benchmark_results,
            summary=champion_benchmark_summary,
            title="Level 3 Baseline Benchmark Report",
        ),
        encoding="utf-8",
    )

    candidate_agents = seed_candidate_agents
    candidate_system = seed_candidate_system
    iterations: list[JSONDict] = []
    stop_reason = "max_steps_reached"

    for step_index in range(1, resolved_max_steps + 1):
        step_dir = steps_dir / f"step_{step_index:02d}"
        step_dir.mkdir(parents=True, exist_ok=True)
        champion_label_before_step = champion_label
        champion_pass_rate_before_step = champion_pass_rate
        _emit_progress(
            progress_callback,
            f"[optimizer step {step_index}/{resolved_max_steps}] comparing champion '{champion_label}' against candidate",
        )

        pairwise_results, pairwise_summary = _run_pairwise_step(
            snapshots=snapshots,
            client=client,
            reviewer_model=config.model,
            grader_model=config.grader_model,
            experiment_agents=experiment_agents,
            champion_agents=champion_agents,
            champion_system=champion_system,
            candidate_agents=candidate_agents,
            candidate_system=candidate_system,
            pairwise_judge_system=pairwise_judge_system,
            review_schema=review_schema,
            pairwise_schema=pairwise_schema,
            progress_callback=progress_callback,
            progress_prefix=f"[pairwise step {step_index}]",
        )
        candidate_benchmark_results, candidate_benchmark_summary = _run_pointwise_benchmark(
            snapshots=snapshots,
            client=client,
            reviewer_model=config.model,
            grader_model=config.grader_model,
            reviewer_system=candidate_system,
            agents_md=candidate_agents,
            grader_system=benchmark_grader_system,
            review_schema=review_schema,
            benchmark_schema=benchmark_schema,
            progress_callback=progress_callback,
            progress_prefix=f"[benchmark step {step_index}]",
        )

        _write_json(step_dir / "pairwise_results.json", pairwise_results)
        _write_json(step_dir / "pairwise_summary.json", pairwise_summary)
        _write_json(step_dir / "benchmark_results.json", candidate_benchmark_results)
        _write_json(step_dir / "benchmark_summary.json", candidate_benchmark_summary)
        (step_dir / "pairwise_report.html").write_text(
            render_pairwise_report_html(results=pairwise_results, summary=pairwise_summary),
            encoding="utf-8",
        )
        (step_dir / "benchmark_report.html").write_text(
            render_report_html(
                results=candidate_benchmark_results,
                summary=candidate_benchmark_summary,
                title=f"Level 3 Candidate Benchmark Report Step {step_index}",
            ),
            encoding="utf-8",
        )

        candidate_win_rate = float(pairwise_summary.get("candidate_win_rate", 0) or 0)
        baseline_win_rate = float(pairwise_summary.get("baseline_win_rate", 0) or 0)
        candidate_pass_rate = float(candidate_benchmark_summary.get("pass_rate", 0) or 0)
        candidate_composite_score = (
            config.pairwise_weight * candidate_win_rate + config.benchmark_weight * candidate_pass_rate
        )
        champion_reference_score = (
            config.pairwise_weight * baseline_win_rate + config.benchmark_weight * champion_pass_rate
        )
        benchmark_guardrail_ok = candidate_pass_rate + config.benchmark_guardrail >= champion_pass_rate
        promoted = benchmark_guardrail_ok and candidate_composite_score > champion_reference_score

        optimizer_output: JSONDict | None = None
        optimizer_rationale = ""

        if promoted:
            champion_agents = candidate_agents
            champion_system = candidate_system
            champion_pass_rate = candidate_pass_rate
            champion_label = f"step_{step_index:02d}_candidate"

        step_record: JSONDict = {
            "step": step_index,
            "champion_label_before_step": champion_label_before_step,
            "candidate_win_rate": candidate_win_rate,
            "baseline_win_rate": baseline_win_rate,
            "tie_rate": float(pairwise_summary.get("tie_rate", 0) or 0),
            "candidate_pass_rate": candidate_pass_rate,
            "champion_pass_rate_reference": champion_pass_rate_before_step,
            "candidate_composite_score": candidate_composite_score,
            "champion_reference_score": champion_reference_score,
            "benchmark_guardrail_ok": benchmark_guardrail_ok,
            "promoted_candidate": promoted,
            "champion_label_after_step": champion_label,
            "pairwise_summary": pairwise_summary,
            "benchmark_summary": candidate_benchmark_summary,
            "candidate_agents_md": candidate_agents,
            "candidate_reviewer_system": candidate_system,
        }

        if promoted and candidate_composite_score >= resolved_score_threshold:
            stop_reason = "score_threshold_reached"
            step_record["stop_reason"] = stop_reason
            iterations.append(step_record)
            break

        if step_index == resolved_max_steps:
            step_record["stop_reason"] = stop_reason
            iterations.append(step_record)
            break

        optimizer_output = _run_json_schema_completion(
            client=client,
            model=config.optimizer_model,
            system_prompt=optimizer_system,
            user_content=build_optimizer_input(
                experiment_agents=experiment_agents,
                champion_label=champion_label,
                champion_agents=champion_agents,
                champion_system=champion_system,
                candidate_agents=candidate_agents,
                candidate_system=candidate_system,
                pairwise_summary=pairwise_summary,
                pairwise_results=pairwise_results,
                candidate_benchmark_summary=candidate_benchmark_summary,
                candidate_benchmark_results=candidate_benchmark_results,
                score_threshold=resolved_score_threshold,
                pairwise_weight=config.pairwise_weight,
                benchmark_weight=config.benchmark_weight,
                benchmark_guardrail=config.benchmark_guardrail,
            ),
            schema_name="optimizer_revision",
            schema=optimizer_schema,
        )
        optimizer_rationale = str(optimizer_output.get("rationale") or "").strip()
        candidate_agents = str(optimizer_output.get("candidate_agents_md") or "").strip()
        candidate_system = str(optimizer_output.get("candidate_reviewer_system") or "").strip()
        step_record["optimizer_rationale"] = optimizer_rationale
        step_record["next_candidate_agents_md"] = candidate_agents
        step_record["next_candidate_reviewer_system"] = candidate_system
        iterations.append(step_record)

        _write_json(step_dir / "optimizer_output.json", optimizer_output)
        (step_dir / "next_candidate_AGENTS.md").write_text(candidate_agents + "\n", encoding="utf-8")
        (step_dir / "next_candidate_reviewer_system.txt").write_text(
            candidate_system + "\n", encoding="utf-8"
        )
        _emit_progress(
            progress_callback,
            f"[optimizer step {step_index}/{resolved_max_steps}] generated next candidate revision",
        )

    final_summary = summarize_optimizer_iterations(
        iterations=iterations,
        champion_label=champion_label,
        champion_pass_rate=champion_pass_rate,
        stop_reason=stop_reason,
        max_steps=resolved_max_steps,
        score_threshold=resolved_score_threshold,
    )
    return write_optimizer_results(
        run_dir=run_dir,
        iterations=iterations,
        summary=final_summary,
        final_champion_agents=champion_agents,
        final_champion_system=champion_system,
    )


def render_optimizer_report(*, run_dir: Path) -> Path:
    iterations = json.loads((run_dir / "iterations.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    report_path = run_dir / "report.html"
    report_path.write_text(
        render_optimizer_report_html(iterations=iterations, summary=summary),
        encoding="utf-8",
    )
    return report_path


def build_optimizer_input(
    *,
    experiment_agents: str,
    champion_label: str,
    champion_agents: str,
    champion_system: str,
    candidate_agents: str,
    candidate_system: str,
    pairwise_summary: JSONDict,
    pairwise_results: list[JSONDict],
    candidate_benchmark_summary: JSONDict,
    candidate_benchmark_results: list[JSONDict],
    score_threshold: float,
    pairwise_weight: float,
    benchmark_weight: float,
    benchmark_guardrail: float,
) -> str:
    pairwise_examples = _select_pairwise_examples(pairwise_results)
    benchmark_examples = _select_benchmark_examples(candidate_benchmark_results)
    return "\n\n".join(
        [
            "Optimization objective:\n" + (experiment_agents or "(empty)"),
            f"Champion label:\n{champion_label}",
            "Champion AGENTS.md:\n" + champion_agents,
            "Champion reviewer system prompt:\n" + champion_system,
            "Current candidate AGENTS.md:\n" + candidate_agents,
            "Current candidate reviewer system prompt:\n" + candidate_system,
            "Composite scoring:\n"
            + json.dumps(
                {
                    "score_threshold": score_threshold,
                    "pairwise_weight": pairwise_weight,
                    "benchmark_weight": benchmark_weight,
                    "benchmark_guardrail": benchmark_guardrail,
                },
                indent=2,
                ensure_ascii=False,
            ),
            "Latest pairwise summary:\n" + json.dumps(pairwise_summary, indent=2, ensure_ascii=False),
            "Representative pairwise examples:\n" + json.dumps(pairwise_examples, indent=2, ensure_ascii=False),
            "Latest benchmark summary:\n"
            + json.dumps(candidate_benchmark_summary, indent=2, ensure_ascii=False),
            "Representative benchmark examples:\n"
            + json.dumps(benchmark_examples, indent=2, ensure_ascii=False),
        ]
    )


def summarize_optimizer_iterations(
    *,
    iterations: list[JSONDict],
    champion_label: str,
    champion_pass_rate: float,
    stop_reason: str,
    max_steps: int,
    score_threshold: float,
) -> JSONDict:
    best_iteration = max(
        iterations,
        key=lambda row: float(row.get("candidate_composite_score", 0) or 0),
        default={},
    )
    return {
        "steps_run": len(iterations),
        "max_steps": max_steps,
        "score_threshold": score_threshold,
        "stop_reason": stop_reason,
        "final_champion_label": champion_label,
        "final_champion_pass_rate": champion_pass_rate,
        "best_step": best_iteration.get("step", 0),
        "best_candidate_composite_score": best_iteration.get("candidate_composite_score", 0),
        "best_candidate_win_rate": best_iteration.get("candidate_win_rate", 0),
        "best_candidate_pass_rate": best_iteration.get("candidate_pass_rate", 0),
    }


def write_optimizer_results(
    *,
    run_dir: Path,
    iterations: list[JSONDict],
    summary: JSONDict,
    final_champion_agents: str,
    final_champion_system: str,
) -> tuple[RunArtifacts, JSONDict]:
    run_dir.mkdir(parents=True, exist_ok=True)
    iterations_json = run_dir / "iterations.json"
    iterations_csv = run_dir / "iterations.csv"
    summary_json = run_dir / "summary.json"
    report_html = run_dir / "report.html"
    final_agents_path = run_dir / "final_candidate_AGENTS.md"
    final_system_path = run_dir / "final_candidate_reviewer_system.txt"

    _write_json(iterations_json, iterations)
    _write_json(summary_json, summary)
    _write_csv(iterations_csv, iterations)
    report_html.write_text(
        render_optimizer_report_html(iterations=iterations, summary=summary),
        encoding="utf-8",
    )
    final_agents_path.write_text(final_champion_agents + "\n", encoding="utf-8")
    final_system_path.write_text(final_champion_system + "\n", encoding="utf-8")

    artifacts = RunArtifacts(
        run_dir=run_dir,
        results_json=iterations_json,
        results_csv=iterations_csv,
        summary_json=summary_json,
        report_html=report_html,
    )
    return artifacts, summary


def render_optimizer_report_html(*, iterations: list[JSONDict], summary: JSONDict) -> str:
    cards = "".join(
        _render_card(label, summary.get(key))
        for label, key in [
            ("Steps run", "steps_run"),
            ("Best step", "best_step"),
            ("Best composite", "best_candidate_composite_score"),
            ("Best pairwise win", "best_candidate_win_rate"),
            ("Best benchmark pass", "best_candidate_pass_rate"),
            ("Final champion", "final_champion_label"),
            ("Stop reason", "stop_reason"),
        ]
    )
    rows = "".join(_render_optimizer_row(iteration) for iteration in iterations)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Level 3 Optimization Harness Report</title>
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
  </style>
</head>
<body>
  <h1>Level 3 Optimization Harness Report</h1>
  <p class="meta">Multi-step optimization history with pairwise and pointwise guardrails.</p>
  <div class="cards">{cards}</div>
  <table>
    <thead>
      <tr>
        <th style="width: 8%">Step</th>
        <th style="width: 10%">Candidate Win</th>
        <th style="width: 10%">Benchmark Pass</th>
        <th style="width: 10%">Composite</th>
        <th style="width: 10%">Promoted</th>
        <th style="width: 12%">Guardrail</th>
        <th style="width: 20%">Optimizer Rationale</th>
        <th style="width: 20%">Stop Reason</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>
"""


def _run_pairwise_step(
    *,
    snapshots: list[JSONDict],
    client: object,
    reviewer_model: str,
    grader_model: str,
    experiment_agents: str,
    champion_agents: str,
    champion_system: str,
    candidate_agents: str,
    candidate_system: str,
    pairwise_judge_system: str,
    review_schema: JSONDict,
    pairwise_schema: JSONDict,
    progress_callback: Callable[[str], None] | None,
    progress_prefix: str,
) -> tuple[list[JSONDict], JSONDict]:
    config = HarnessConfig(model=reviewer_model, grader_model=grader_model)
    results: list[JSONDict] = []
    total_snapshots = len(snapshots)
    for index, snapshot in enumerate(snapshots, start=1):
        pr_number = snapshot.get("number")
        _emit_progress(
            progress_callback,
            f"{progress_prefix} [{index}/{total_snapshots}] PR #{pr_number}",
        )
        try:
            baseline_review = _run_json_schema_completion(
                client=client,
                model=reviewer_model,
                system_prompt=champion_system,
                user_content=build_reviewer_input(snapshot, champion_agents),
                schema_name="optimizer_baseline_review_output",
                schema=review_schema,
            )
            candidate_review = _run_json_schema_completion(
                client=client,
                model=reviewer_model,
                system_prompt=candidate_system,
                user_content=build_reviewer_input(snapshot, candidate_agents),
                schema_name="optimizer_candidate_review_output",
                schema=review_schema,
            )
            judgment = _run_json_schema_completion(
                client=client,
                model=grader_model,
                system_prompt=pairwise_judge_system,
                user_content=build_pairwise_judge_input(
                    snapshot=snapshot,
                    experiment_agents=experiment_agents,
                    baseline_agents=champion_agents,
                    candidate_agents=candidate_agents,
                    baseline_review=baseline_review,
                    candidate_review=candidate_review,
                ),
                schema_name="optimizer_pairwise_judgment",
                schema=pairwise_schema,
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
        except Exception as exc:  # pragma: no cover - exercised through CLI smoke paths
            results.append(build_pairwise_failure_row(snapshot=snapshot, error_message=str(exc), config=config))
    return results, summarize_pairwise_results(results)


def _run_pointwise_benchmark(
    *,
    snapshots: list[JSONDict],
    client: object,
    reviewer_model: str,
    grader_model: str,
    reviewer_system: str,
    agents_md: str,
    grader_system: str,
    review_schema: JSONDict,
    benchmark_schema: JSONDict,
    progress_callback: Callable[[str], None] | None,
    progress_prefix: str,
) -> tuple[list[JSONDict], JSONDict]:
    config = HarnessConfig(model=reviewer_model, grader_model=grader_model)
    results: list[JSONDict] = []
    total_snapshots = len(snapshots)
    for index, snapshot in enumerate(snapshots, start=1):
        pr_number = snapshot.get("number")
        _emit_progress(
            progress_callback,
            f"{progress_prefix} [{index}/{total_snapshots}] PR #{pr_number}",
        )
        try:
            review_output = _run_json_schema_completion(
                client=client,
                model=reviewer_model,
                system_prompt=reviewer_system,
                user_content=build_reviewer_input(snapshot, agents_md),
                schema_name="optimizer_benchmark_review_output",
                schema=review_schema,
            )
            grade_output = _run_json_schema_completion(
                client=client,
                model=grader_model,
                system_prompt=grader_system,
                user_content=build_grader_input(snapshot, agents_md, review_output),
                schema_name="optimizer_benchmark_grade",
                schema=benchmark_schema,
            )
            results.append(
                build_result_row(
                    snapshot=snapshot,
                    review_output=review_output,
                    grade_output=grade_output,
                    config=config,
                )
            )
        except Exception as exc:  # pragma: no cover - exercised through CLI smoke paths
            results.append(build_failure_row(snapshot=snapshot, error_message=str(exc), config=config))
    return results, summarize_results(results)


def _select_pairwise_examples(results: list[JSONDict], limit: int = 3) -> list[JSONDict]:
    selected: list[JSONDict] = []
    for winner in ("baseline", "candidate", "tie"):
        matching = [row for row in results if row.get("status") == "ok" and row.get("winner") == winner]
        for row in matching[:limit]:
            selected.append(
                {
                    "pr_number": row.get("pr_number"),
                    "pr_title": row.get("pr_title"),
                    "winner": row.get("winner"),
                    "judge_reason": row.get("judge_reason"),
                    "baseline_summary": row.get("baseline_summary"),
                    "candidate_summary": row.get("candidate_summary"),
                }
            )
    return selected


def _select_benchmark_examples(results: list[JSONDict], limit: int = 5) -> list[JSONDict]:
    failures = [row for row in results if row.get("status") != "ok"][:limit]
    failing_grades = [
        row for row in results if row.get("status") == "ok" and not row.get("grader_overall_pass")
    ][:limit]
    selected = failures + failing_grades
    return [
        {
            "pr_number": row.get("pr_number"),
            "pr_title": row.get("pr_title"),
            "status": row.get("status"),
            "grader_overall_pass": row.get("grader_overall_pass"),
            "grader_reason": row.get("grader_reason"),
            "reviewer_summary": row.get("reviewer_summary"),
            "error_message": row.get("error_message"),
        }
        for row in selected
    ]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[JSONDict]) -> None:
    flattened = [_flatten_row(row) for row in rows]
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


def _render_optimizer_row(iteration: JSONDict) -> str:
    return (
        "<tr>"
        f"<td>{escape(str(iteration.get('step', '')))}</td>"
        f"<td>{escape(_format_metric(iteration.get('candidate_win_rate')))}</td>"
        f"<td>{escape(_format_metric(iteration.get('candidate_pass_rate')))}</td>"
        f"<td>{escape(_format_metric(iteration.get('candidate_composite_score')))}</td>"
        f"<td>{escape(str(iteration.get('promoted_candidate', False)))}</td>"
        f"<td>{escape(str(iteration.get('benchmark_guardrail_ok', False)))}</td>"
        f"<td><pre>{escape(str(iteration.get('optimizer_rationale', '')))}</pre></td>"
        f"<td>{escape(str(iteration.get('stop_reason', '')))}</td>"
        "</tr>"
    )


def _format_metric(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
